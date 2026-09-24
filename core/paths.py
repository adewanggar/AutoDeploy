"""
Path management for AutoDeploy.
Stores configuration, logs, PID, and deployment history in %ProgramData%\\AutoDeploy.
"""

import os
from pathlib import Path

def get_data_dir() -> Path:
    """Returns %ProgramData%\\AutoDeploy or fallback to user local appdata if unavailable."""
    base = os.environ.get("ProgramData") or os.environ.get("ALLUSERSPROFILE") or "C:\\ProgramData"
    data_dir = Path(base) / "AutoDeploy"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fallback to user home directory if ProgramData is not writable
        data_dir = Path.home() / ".autodeploy"
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

DATA_DIR = get_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
HISTORY_PATH = DATA_DIR / "history.jsonl"
LOG_PATH = DATA_DIR / "engine.log"
PID_PATH = DATA_DIR / "engine.pid"
