"""
Configuration management for AutoDeploy.
Handles reading/writing config.json with safe atomic writes and default fallback.
"""

import json
import os
import secrets
from typing import Any, Dict, List, Optional
from core.paths import CONFIG_PATH

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {
      "host": "0.0.0.0",
      "port": 9876
    },
    "telegram": {
      "enabled": False,
      "bot_token": "",
      "chat_id": ""
    },
    "projects": []
}

RESTART_PRESETS = {
    "custom": {
        "label": "Custom Command",
        "command": ""
    },
    "windows_service": {
        "label": "Windows Service (net stop & start)",
        "command": 'net stop "ServiceName" & net start "ServiceName"'
    },
    "nssm": {
        "label": "NSSM Service (nssm restart)",
        "command": 'nssm restart ServiceName'
    },
    "pm2": {
        "label": "PM2 (pm2 restart)",
        "command": 'pm2 restart app-name'
    },
    "docker_compose": {
        "label": "Docker Compose (up -d --build)",
        "command": 'docker compose up -d --build'
    },
    "iis_apppool": {
        "label": "IIS App Pool (appcmd recycle)",
        "command": '%windir%\\system32\\inetsrv\\appcmd recycle apppool /apppool.name:"AppPoolName"'
    },
    "regular_process": {
        "label": "Regular Process (taskkill & start detached)",
        "command": 'taskkill /F /IM app.exe & start "" /D "C:\\apps\\my-app" "app.exe"'
    }
}

def create_default_project(project_id: str = "", name: str = "") -> Dict[str, Any]:
    """Generates a default project configuration dictionary."""
    clean_id = project_id or secrets.token_hex(4)
    return {
        "id": clean_id,
        "name": name or f"Project-{clean_id}",
        "enabled": True,
        "path": r"C:\apps\my-app",
        "remote": "origin",
        "branch": "main",
        "trigger_mode": "both",  # "webhook", "polling", "both"
        "secret": secrets.token_hex(16),
        "polling_interval": 60,
        "steps": [
            "git fetch origin main",
            "git reset --hard origin/main"
        ],
        "restart_command": 'net stop "ServiceName" & net start "ServiceName"',
        "timeout": 300,
        "rollback_on_failure": True,
        "shell": "cmd"  # "cmd" or "powershell"
    }

def load_config() -> Dict[str, Any]:
    """Loads configuration from config.json, creating with defaults if absent."""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure top-level sections exist
        if "server" not in data:
            data["server"] = dict(DEFAULT_CONFIG["server"])
        if "telegram" not in data:
            data["telegram"] = dict(DEFAULT_CONFIG["telegram"])
        if "projects" not in data:
            data["projects"] = []
        return data
    except Exception as exc:
        print(f"[Config] Error reading {CONFIG_PATH}: {exc}. Using defaults.")
        return dict(DEFAULT_CONFIG)

def save_config(config_data: Dict[str, Any]) -> None:
    """Saves configuration atomically to config.json."""
    temp_path = CONFIG_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    # Atomic replace
    os.replace(temp_path, CONFIG_PATH)

def get_config_mtime() -> float:
    """Returns mtime of config.json or 0.0 if not found."""
    try:
        return os.path.getmtime(CONFIG_PATH)
    except OSError:
        return 0.0

def find_project_by_id(config_data: Dict[str, Any], project_id: str) -> Optional[Dict[str, Any]]:
    for proj in config_data.get("projects", []):
        if proj.get("id") == project_id:
            return proj
    return None
