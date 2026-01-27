import json
import os
from pathlib import Path
from typing import Any, Dict


def _resolve_output_dir() -> Path:
    env_dir = os.getenv("QUALITY_REPORT_DIR")
    base = Path(env_dir) if env_dir else Path("output") / "quality_reports"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _timings_from_metrics(metrics: Any) -> Dict[str, float]:
    if metrics is None:
        return {}
    if not isinstance(metrics, dict) and hasattr(metrics, "to_dict"):
        metrics = metrics.to_dict()
    if not isinstance(metrics, dict):
        return {}

    timings: Dict[str, float] = {}
    for stage in metrics.get("stages", []) or []:
        name = stage.get("name")
        if name:
            timings[name] = stage.get("duration_ms")
    total = metrics.get("total_duration_ms")
    if total is not None:
        timings["total"] = total
    return timings


def write_quality_report(result) -> str:
    ctx = result.task
    output_dir = _resolve_output_dir()
    report_path = output_dir / f"{ctx.task_id}.json"

    data = {
        "task_id": str(ctx.task_id),
        "image_path": ctx.image_path,
        "output_path": ctx.output_path,
        "target_language": ctx.target_language,
        "timings_ms": _timings_from_metrics(result.metrics),
        "regions": [
            {
                "region_id": str(r.region_id),
                "source_text": r.source_text,
                "target_text": r.target_text,
                "confidence": r.confidence,
                "box_2d": r.box_2d.model_dump() if r.box_2d else None,
                "quality_score": None,
            }
            for r in (ctx.regions or [])
        ],
    }

    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(report_path)
