"""
Core deployment executor for AutoDeploy.
Executes configured steps, handles restart command, automatic rollback on failure,
manages per-project deployment locks, queues at most 1 pending trigger, and logs to history.
"""

import datetime
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.history import append_history
from core.telegram import format_deploy_notification, send_telegram_notification

_locks_guard = threading.Lock()
_project_locks: Dict[str, threading.Lock] = {}
_project_pending: Dict[str, bool] = {}
_project_running: Dict[str, bool] = {}

def is_project_deploying(project_id: str) -> bool:
    """Returns True if a deployment is currently running for project_id."""
    with _locks_guard:
        return _project_running.get(project_id, False)

def _get_project_lock(project_id: str) -> threading.Lock:
    with _locks_guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]

def run_shell_command(
    command: str,
    cwd: str,
    shell_type: str = "cmd",
    timeout: int = 300
) -> Tuple[int, str, float]:
    """
    Executes a shell command in the specified directory.
    Returns (exit_code, combined_output, duration_seconds).
    Security: The command MUST come from verified configuration only.
    """
    start_time = time.time()
    if shell_type.lower() == "powershell":
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NonInteractive", "-Command", command]
    else:
        # Use string command line to prevent list2cmdline from mangling quotes for cmd.exe
        args = f'cmd.exe /s /c "{command}"'

    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        try:
            output, _ = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
            output += f"\n[AutoDeploy Error] Command timed out after {timeout} seconds."
            exit_code = -1
    except Exception as exc:
        output = f"[AutoDeploy Error] Failed to execute process: {str(exc)}"
        exit_code = -2

    duration = time.time() - start_time
    return exit_code, output.strip(), duration

def git_get_head_commit(repo_path: str) -> str:
    """Gets current commit hash (HEAD) in repo_path."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
            check=True
        )
        return res.stdout.strip()
    except Exception:
        return ""

def git_get_commit_info(repo_path: str) -> Tuple[str, str]:
    """Gets (author_name, commit_message) for current HEAD."""
    try:
        author_res = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%an"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15
        )
        msg_res = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%B"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15
        )
        return author_res.stdout.strip(), msg_res.stdout.strip()
    except Exception:
        return "", ""

def git_get_remote_commit(repo_path: str, remote: str = "origin", branch: str = "main") -> Optional[str]:
    """Queries remote repository commit hash via git ls-remote without fetching objects."""
    try:
        res = subprocess.run(
            ["git", "ls-remote", remote, branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        # Output format: "<sha>\trefs/heads/<branch>" or "<sha>\thead"
        line = res.stdout.strip().splitlines()
        if line:
            parts = line[0].split()
            if parts:
                return parts[0].strip()
    except Exception as exc:
        print(f"[Git Remote] Failed ls-remote on {repo_path} ({remote}/{branch}): {exc}")
    return None

def trigger_deploy(
    project: Dict[str, Any],
    trigger_type: str = "manual",
    author: str = "",
    commit_msg: str = "",
    telegram_config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Triggers deployment for a project.
    If a deploy is already active, queues exactly 1 pending deployment.
    Returns (success_queued_or_started, message).
    """
    proj_id = project.get("id", "")
    if not proj_id:
        return False, "Project ID missing"
    
    with _locks_guard:
        if _project_running.get(proj_id, False):
            _project_pending[proj_id] = True
            return True, f"Deploy already in progress for '{project.get('name')}'. Queued next run."
        
        _project_running[proj_id] = True
        _project_pending[proj_id] = False

    # Start deployment thread
    thread = threading.Thread(
        target=_deploy_worker_loop,
        args=(project, trigger_type, author, commit_msg, telegram_config),
        daemon=True,
        name=f"deploy-{proj_id}"
    )
    thread.start()
    return True, f"Deployment started for '{project.get('name')}'"

def _deploy_worker_loop(
    project: Dict[str, Any],
    initial_trigger: str,
    initial_author: str,
    initial_msg: str,
    telegram_config: Optional[Dict[str, Any]]
) -> None:
    proj_id = project.get("id", "")
    current_trigger = initial_trigger
    current_author = initial_author
    current_msg = initial_msg

    lock = _get_project_lock(proj_id)

    try:
        with lock:
            while True:
                _execute_single_deploy(project, current_trigger, current_author, current_msg, telegram_config)
                
                with _locks_guard:
                    if _project_pending.get(proj_id, False):
                        _project_pending[proj_id] = False
                        current_trigger = "queued"
                        current_author = ""
                        current_msg = "Queued deployment trigger"
                    else:
                        _project_running[proj_id] = False
                        break
    finally:
        with _locks_guard:
            _project_running[proj_id] = False
            _project_pending[proj_id] = False

def _execute_single_deploy(
    project: Dict[str, Any],
    trigger_type: str,
    author: str,
    commit_msg: str,
    telegram_config: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    start_ts = time.time()
    iso_start = datetime.datetime.now().isoformat()
    repo_path = project.get("path", "")
    shell_type = project.get("shell", "cmd")
    timeout = int(project.get("timeout", 300))
    rollback_enabled = bool(project.get("rollback_on_failure", True))
    restart_cmd = project.get("restart_command", "").strip()
    steps = project.get("steps", [])

    steps_log: List[Dict[str, Any]] = []
    status = "success"
    error_summary = ""

    # 1. Capture commit before deployment
    old_commit = git_get_head_commit(repo_path)

    # Validate directory
    if not Path(repo_path).exists():
        status = "failed"
        error_summary = f"Repo path does not exist: {repo_path}"
        steps_log.append({
            "command": "check_directory",
            "exit_code": 1,
            "output": error_summary,
            "duration": 0.0
        })
    else:
        # 2. Run sequential steps
        for step in steps:
            step_cmd = step.strip()
            if not step_cmd:
                continue
            
            exit_code, output, duration = run_shell_command(
                step_cmd, cwd=repo_path, shell_type=shell_type, timeout=timeout
            )
            steps_log.append({
                "command": step_cmd,
                "exit_code": exit_code,
                "output": output,
                "duration": round(duration, 2)
            })

            if exit_code != 0:
                status = "failed"
                error_summary = f"Step failed [code {exit_code}]: {step_cmd}\n{output}"
                break

        # 3. If steps succeeded, execute restart_command
        if status == "success" and restart_cmd:
            exit_code, output, duration = run_shell_command(
                restart_cmd, cwd=repo_path, shell_type=shell_type, timeout=timeout
            )
            steps_log.append({
                "command": restart_cmd,
                "exit_code": exit_code,
                "output": output,
                "duration": round(duration, 2)
            })
            if exit_code != 0:
                status = "failed"
                error_summary = f"Restart command failed [code {exit_code}]: {restart_cmd}\n{output}"

        # 4. If failed and rollback is enabled, rollback to old_commit
        if status == "failed" and rollback_enabled and old_commit:
            rollback_cmd = f"git reset --hard {old_commit}"
            rb_exit, rb_output, rb_dur = run_shell_command(
                rollback_cmd, cwd=repo_path, shell_type=shell_type, timeout=timeout
            )
            steps_log.append({
                "command": f"[ROLLBACK] {rollback_cmd}",
                "exit_code": rb_exit,
                "output": rb_output,
                "duration": round(rb_dur, 2)
            })

            if restart_cmd:
                rb_restart_exit, rb_restart_out, rb_restart_dur = run_shell_command(
                    restart_cmd, cwd=repo_path, shell_type=shell_type, timeout=timeout
                )
                steps_log.append({
                    "command": f"[ROLLBACK RESTART] {restart_cmd}",
                    "exit_code": rb_restart_exit,
                    "output": rb_restart_out,
                    "duration": round(rb_restart_dur, 2)
                })

            status = "rolled_back"

    # End timing and fetch current git status
    total_duration = time.time() - start_ts
    new_commit = git_get_head_commit(repo_path)
    git_author, git_msg = git_get_commit_info(repo_path)
    
    final_author = author or git_author or "AutoDeploy"
    final_msg = commit_msg or git_msg or "No commit message"

    # 5. Build and save history entry
    history_entry = {
        "id": f"{int(start_ts*1000)}",
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "timestamp": iso_start,
        "duration_seconds": round(total_duration, 2),
        "trigger": trigger_type,
        "status": status,
        "old_commit": old_commit,
        "new_commit": new_commit,
        "author": final_author,
        "commit_message": final_msg,
        "error_summary": error_summary,
        "steps_log": steps_log
    }
    append_history(history_entry)

    # 6. Send optional Telegram notification
    if telegram_config and telegram_config.get("enabled"):
        bot_token = telegram_config.get("bot_token", "").strip()
        chat_id = telegram_config.get("chat_id", "").strip()
        if bot_token and chat_id:
            msg = format_deploy_notification(
                project_name=project.get("name", "Unknown"),
                status=status,
                duration=total_duration,
                trigger=trigger_type,
                old_commit=old_commit,
                new_commit=new_commit,
                commit_msg=final_msg,
                author=final_author,
                error_detail=error_summary
            )
            send_telegram_notification(bot_token, chat_id, msg)

    return history_entry
