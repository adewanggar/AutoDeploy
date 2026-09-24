"""
Deployment history management for AutoDeploy.
Stores entries in JSONL format, keeping at most 500 latest runs.
"""

import json
import threading
from typing import Any, Dict, List
from core.paths import HISTORY_PATH

_history_lock = threading.Lock()
MAX_HISTORY_ENTRIES = 500

def append_history(entry: Dict[str, Any]) -> None:
    """Appends a deployment entry to history.jsonl and trims to MAX_HISTORY_ENTRIES."""
    with _history_lock:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        
        # Check line count periodically or if exceeding limit
        _trim_history_if_needed()

def _trim_history_if_needed() -> None:
    """Trims history file to the latest MAX_HISTORY_ENTRIES."""
    if not HISTORY_PATH.exists():
        return
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        
        if len(lines) > MAX_HISTORY_ENTRIES:
            trimmed = lines[-MAX_HISTORY_ENTRIES:]
            temp_path = HISTORY_PATH.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                for ln in trimmed:
                    f.write(ln + "\n")
            temp_path.replace(HISTORY_PATH)
    except Exception as exc:
        print(f"[History] Error trimming history: {exc}")

def load_history(limit: int = MAX_HISTORY_ENTRIES) -> List[Dict[str, Any]]:
    """Loads history entries in reverse chronological order (newest first)."""
    if not HISTORY_PATH.exists():
        return []
    
    with _history_lock:
        entries: List[Dict[str, Any]] = []
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            print(f"[History] Error reading history: {exc}")
            return []
        
        # Return newest first
        entries.reverse()
        return entries[:limit]
