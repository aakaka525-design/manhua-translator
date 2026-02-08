import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import List

from fastapi import APIRouter, Request

from app.deps import get_settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/models")
async def get_models_status(request: Request):
    registry = getattr(request.app.state, "model_registry", None)
    if registry is None:
        return {
            "ppocr_det": {"status": "missing"},
            "ppocr_rec": {"status": "missing"},
            "lama": {"status": "missing"},
        }
    return registry.snapshot()


def _pkg_version(*names: str) -> str:
    for name in names:
        try:
            return version(name)
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    return "missing"


def _module_version(module_name: str) -> str:
    try:
        module = __import__(module_name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception:
        return "missing"


@router.get("/runtime")
async def get_runtime_status(request: Request):
    settings = get_settings()
    registry = getattr(request.app.state, "model_registry", None)
    model_snapshot = registry.snapshot() if registry else {}

    ocr_cache_dir = Path(os.getenv("OCR_RESULT_CACHE_DIR", "temp/ocr_cache")).expanduser()

    return {
        "versions": {
            "python": sys.version.split()[0],
            "fastapi": _pkg_version("fastapi"),
            "pydantic": _pkg_version("pydantic"),
            "paddle": _pkg_version("paddlepaddle"),
            "paddleocr": _pkg_version("paddleocr"),
            "opencv": _module_version("cv2"),
            "torch": _pkg_version("torch"),
        },
        "settings": {
            "source_language": settings.source_language,
            "target_language": settings.target_language,
            "ocr": {
                "fail_on_empty": os.getenv("OCR_FAIL_ON_EMPTY", "1"),
                "result_cache_enable": os.getenv("OCR_RESULT_CACHE_ENABLE", "1"),
                "cache_empty_results": os.getenv("OCR_CACHE_EMPTY_RESULTS", "0"),
                "crosspage_edge_enable": os.getenv("OCR_CROSSPAGE_EDGE_ENABLE", "1"),
                "edge_tile_enable": os.getenv("OCR_EDGE_TILE_ENABLE", "0"),
            },
            "translator": {
                "ai_provider": os.getenv("AI_PROVIDER", "ppio"),
                "ai_translate_fastfail": os.getenv("AI_TRANSLATE_FASTFAIL", "1"),
            },
        },
        "paths": {
            "data_dir": str(Path(settings.data_dir).expanduser().resolve()),
            "output_dir": str(Path(settings.output_dir).expanduser().resolve()),
            "temp_dir": str(Path(settings.temp_dir).expanduser().resolve()),
            "ocr_cache_dir": str(ocr_cache_dir.resolve()),
        },
        "model_registry": model_snapshot,
    }

@router.get("/logs", response_model=List[str])
async def get_system_logs(lines: int = 100):
    """
    Get the last N lines of the system log.
    """
    log_file = Path("logs")
    # Log files are timestamped, e.g., logs/20260126_app.log. 
    # Or just app.log if configured that way. 
    # core/logging_config.py says: LOG_DIR = ... / "logs". 
    # And setup_logging(log_file="app.log") creates f"{date_str}_{log_file}"
    
    # We need to find the latest log file.
    if not log_file.exists():
        # Fallback to checking core/logging_config.py LOG_DIR location
        # It says Path(__file__).parent.parent / "logs" which is project_root/logs
        pass

    log_dir = Path("logs")
    if not log_dir.exists():
         return ["Log directory not found"]
    
    # Find all files ending in _app.log and sort by name (date)
    log_files = sorted(log_dir.glob("*_app.log"))
    
    if not log_files:
        return ["No log files found"]
        
    latest_log = log_files[-1]
    
    try:
        with open(latest_log, "r", encoding="utf-8") as f:
            content = f.readlines()
            return content[-lines:]
    except Exception as e:
        return [f"Error reading log file: {str(e)}"]
