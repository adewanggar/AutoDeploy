"""
Process control helpers for AutoDeploy Engine.
Provides status detection, start, stop, restart, and Windows Task Scheduler installation.
"""

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from core.paths import PID_PATH

def is_pid_alive(pid: int) -> bool:
    """Checks if a Windows process ID is alive using Windows Win32 API."""
    if pid <= 0:
        return False
    PROCESS_QUERY_INFORMATION = 0x0400
    STILL_ACTIVE = 259
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == STILL_ACTIVE
        return False
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

def get_engine_status() -> Tuple[bool, Optional[int]]:
    """
    Returns (is_running, pid).
    Cleans up stale engine.pid if process is dead.
    """
    if not PID_PATH.exists():
        return False, None
    try:
        content = PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(content)
        if is_pid_alive(pid):
            return True, pid
        # Process is dead, remove stale pid
        try:
            PID_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        return False, None
    except Exception:
        return False, None

def get_python_executable(gui_or_headless: bool = True) -> str:
    """Returns pythonw.exe if available to avoid popping console windows, else sys.executable."""
    if gui_or_headless:
        pw = Path(sys.executable).with_name("pythonw.exe")
        if pw.exists():
            return str(pw)
    return sys.executable

def start_engine_process() -> Tuple[bool, str]:
    """Starts the engine headless in the background detached from the current process."""
    running, pid = get_engine_status()
    if running:
        return True, f"Engine is already running (PID: {pid})"
    
    main_py = Path(__file__).parent.parent / "main.py"
    if not main_py.exists():
        return False, f"Cannot find {main_py}"
    
    python_bin = get_python_executable(gui_or_headless=True)
    # Flags for detached Windows process with no window and independent process group
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    try:
        proc = subprocess.Popen(
            [python_bin, str(main_py.resolve()), "--engine"],
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )
        # Give it a moment to write PID
        for _ in range(10):
            time.sleep(0.3)
            alive, active_pid = get_engine_status()
            if alive:
                return True, f"Engine started successfully (PID: {active_pid})"
        return True, f"Engine spawned (PID: {proc.pid})"
    except Exception as exc:
        return False, f"Failed to start engine: {exc}"

def stop_engine_process() -> Tuple[bool, str]:
    """Stops the running engine process by PID."""
    running, pid = get_engine_status()
    if not running or not pid:
        return True, "Engine is not running"
    
    try:
        # Use taskkill on Windows to ensure termination of tree
        res = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True,
            text=True
        )
        PID_PATH.unlink(missing_ok=True)
        return True, f"Engine stopped (PID: {pid})"
    except Exception as exc:
        return False, f"Failed to stop engine: {exc}"

def restart_engine_process() -> Tuple[bool, str]:
    """Restarts the engine process."""
    stop_engine_process()
    time.sleep(1)
    return start_engine_process()

def get_task_scheduler_cmd() -> str:
    """Returns the schtasks command string for registering AutoDeploy as a Windows startup service."""
    main_py = Path(__file__).parent.parent / "main.py"
    python_bin = get_python_executable(gui_or_headless=True)
    # Runs on system startup under SYSTEM account with highest privileges
    return (
        f'schtasks /create /tn "AutoDeployEngine" '
        f'/tr "\"{python_bin}\" \"{main_py.resolve()}\" --engine" '
        f'/sc onstart /ru SYSTEM /rl HIGHEST /f'
    )
