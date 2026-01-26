from fastapi import APIRouter, HTTPException
from pathlib import Path
from typing import List

router = APIRouter(prefix="/system", tags=["system"])

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
