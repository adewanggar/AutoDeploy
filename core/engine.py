"""
Headless deployment engine for AutoDeploy.
Runs webhook HTTP server (ThreadingHTTPServer) and background Git polling workers.
Watches config.json for real-time auto-reloading without restart.
Standard library only: http.server, subprocess, threading, hmac, urllib, json, hashlib.
"""

import hashlib
import hmac
import http.server
import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import get_config_mtime, load_config
from core.deployer import (
    git_get_head_commit,
    git_get_remote_commit,
    is_project_deploying,
    trigger_deploy,
)
from core.paths import LOG_PATH, PID_PATH

MAX_BODY_SIZE = 1024 * 1024  # 1 MB

class EngineState:
    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.config_mtime: float = 0.0
        self.start_time: float = time.time()
        self.is_running: bool = True
        self.lock = threading.Lock()
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        # Track last known remote commit per project to avoid redundant triggers
        self.last_remote_commits: Dict[str, str] = {}
        self.last_poll_timestamps: Dict[str, float] = {}

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            for proj in self.config.get("projects", []):
                if proj.get("id") == project_id:
                    return dict(proj)
        return None

    def get_telegram_config(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.config.get("telegram", {}))

state = EngineState()

def setup_logging() -> None:
    """Configures logging to both LOG_PATH and console with rotation/formatting."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True
    )

class WebhookRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "AutoDeployEngine/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            uptime = time.time() - state.start_time
            with state.lock:
                projects_summary = [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "enabled": p.get("enabled", True),
                        "trigger_mode": p.get("trigger_mode", "both"),
                        "deploying": is_project_deploying(p.get("id", ""))
                    }
                    for p in state.config.get("projects", [])
                ]
            self._send_json_response(200, {
                "status": "ok",
                "uptime_seconds": round(uptime, 1),
                "projects_count": len(projects_summary),
                "projects": projects_summary
            })
            return
        
        self._send_json_response(404, {"error": "Not found"})

    def do_POST(self) -> None:
        # Route: /hook/<project_id>
        if self.path.startswith("/hook/"):
            project_id = self.path[len("/hook/"):].strip()
            self._handle_webhook(project_id)
            return

        # Route: /api/deploy/<project_id> (Internal manual trigger via HTTP)
        if self.path.startswith("/api/deploy/"):
            project_id = self.path[len("/api/deploy/"):].strip()
            self._handle_manual_deploy(project_id)
            return

        self._send_json_response(404, {"error": "Not found"})

    def _handle_manual_deploy(self, project_id: str) -> None:
        project = state.get_project(project_id)
        if not project:
            self._send_json_response(404, {"error": f"Project '{project_id}' not found"})
            return
        
        success, msg = trigger_deploy(
            project=project,
            trigger_type="manual",
            author="Manual (GUI/API)",
            commit_msg="Manual deploy triggered via API",
            telegram_config=state.get_telegram_config()
        )
        self._send_json_response(200, {"success": success, "message": msg})

    def _handle_webhook(self, project_id: str) -> None:
        project = state.get_project(project_id)
        if not project:
            logging.warning(f"Webhook request received for unknown project '{project_id}'")
            self._send_json_response(404, {"error": f"Project '{project_id}' not found"})
            return

        if not project.get("enabled", True):
            logging.info(f"Webhook skipped: Project '{project_id}' is disabled.")
            self._send_json_response(200, {"status": "skipped", "message": "Project is disabled"})
            return

        mode = project.get("trigger_mode", "both")
        if mode not in ("webhook", "both"):
            logging.info(f"Webhook skipped: Project '{project_id}' trigger mode is '{mode}' (not webhook)")
            self._send_json_response(200, {"status": "skipped", "message": "Webhook triggers disabled for project"})
            return

        # Check Content-Length and body size limit
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            content_length = 0

        if content_length > MAX_BODY_SIZE:
            logging.warning(f"Webhook rejected for '{project_id}': Body exceeds 1MB limit ({content_length} bytes)")
            self._send_json_response(413, {"error": "Payload Too Large (Max 1MB)"})
            return

        body = self.rfile.read(content_length)

        # HMAC Verification (X-Hub-Signature-256)
        secret = project.get("secret", "").strip()
        sig_header = self.headers.get("X-Hub-Signature-256", "")

        if secret:
            if not sig_header:
                logging.warning(f"Webhook rejected for '{project_id}': Missing X-Hub-Signature-256 header")
                self._send_json_response(403, {"error": "Forbidden: Missing signature header"})
                return

            expected_sig = "sha256=" + hmac.new(
                secret.encode("utf-8"),
                body,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_sig, sig_header):
                logging.warning(f"Webhook rejected for '{project_id}': Invalid signature")
                self._send_json_response(403, {"error": "Forbidden: Signature verification failed"})
                return

        event = self.headers.get("X-GitHub-Event", "push")
        if event == "ping":
            logging.info(f"GitHub ping received for project '{project_id}'")
            self._send_json_response(200, {"status": "pong", "message": "Ping acknowledged"})
            return

        if event != "push":
            logging.info(f"Ignoring GitHub event '{event}' for project '{project_id}'")
            self._send_json_response(200, {"status": "ignored", "event": event})
            return

        # Parse JSON push payload safely
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as exc:
            self._send_json_response(400, {"error": f"Invalid JSON payload: {exc}"})
            return

        # Validate ref matches configured branch
        ref = payload.get("ref", "")
        configured_branch = project.get("branch", "main").strip()
        expected_ref = f"refs/heads/{configured_branch}"

        if ref and ref != expected_ref:
            logging.info(f"Push ref '{ref}' does not match project branch '{configured_branch}'. Skipping deploy.")
            self._send_json_response(200, {
                "status": "ref_ignored",
                "received_ref": ref,
                "expected_ref": expected_ref
            })
            return

        # Extract metadata from payload
        head_commit = payload.get("head_commit") or {}
        author_name = (
            head_commit.get("author", {}).get("name")
            or payload.get("pusher", {}).get("name")
            or "GitHub Webhook"
        )
        commit_msg = head_commit.get("message", "Commit via Webhook")

        logging.info(f"Push event validated for project '{project_id}'. Triggering deploy...")
        success, msg = trigger_deploy(
            project=project,
            trigger_type="webhook",
            author=author_name,
            commit_msg=commit_msg,
            telegram_config=state.get_telegram_config()
        )
        self._send_json_response(200, {"status": "deploy_triggered", "message": msg})

def config_watcher_thread() -> None:
    """Monitors config.json modification time every 3s and auto-reloads changes."""
    logging.info("Config watcher started.")
    while state.is_running:
        try:
            current_mtime = get_config_mtime()
            if current_mtime != state.config_mtime and current_mtime > 0:
                logging.info(f"Configuration change detected. Reloading config...")
                new_cfg = load_config()
                with state.lock:
                    old_port = state.config.get("server", {}).get("port")
                    new_port = new_cfg.get("server", {}).get("port")
                    state.config = new_cfg
                    state.config_mtime = current_mtime
                if old_port and new_port and old_port != new_port:
                    logging.warning(
                        f"Server port changed from {old_port} to {new_port}. "
                        "Port changes take effect upon Engine restart."
                    )
                logging.info(f"Loaded {len(new_cfg.get('projects', []))} projects from config.")
        except Exception as exc:
            logging.error(f"Error in config watcher: {exc}")
        time.sleep(3)

def polling_worker_thread() -> None:
    """Checks remote repository commits for polling-enabled projects."""
    logging.info("Git polling worker started.")
    while state.is_running:
        try:
            with state.lock:
                projects = list(state.config.get("projects", []))
                tg_config = dict(state.config.get("telegram", {}))
            
            now = time.time()
            for project in projects:
                if not state.is_running:
                    break

                if not project.get("enabled", True):
                    continue

                mode = project.get("trigger_mode", "both")
                if mode not in ("polling", "both"):
                    continue

                proj_id = project.get("id", "")
                interval = max(5, int(project.get("polling_interval", 60)))
                last_poll = state.last_poll_timestamps.get(proj_id, 0.0)

                if now - last_poll < interval:
                    continue

                state.last_poll_timestamps[proj_id] = now
                repo_path = project.get("path", "")
                if not Path(repo_path).exists():
                    continue

                remote = project.get("remote", "origin")
                branch = project.get("branch", "main")

                # Fetch remote SHA without full git pull
                remote_sha = git_get_remote_commit(repo_path, remote, branch)
                if not remote_sha or len(remote_sha) < 40:
                    continue

                local_sha = git_get_head_commit(repo_path)
                
                # If remote commit differs from local commit and we haven't already triggered it
                last_seen_remote = state.last_remote_commits.get(proj_id)
                if remote_sha != local_sha and remote_sha != last_seen_remote:
                    logging.info(
                        f"[Polling] New commit detected for '{project.get('name')}' "
                        f"({local_sha[:7]} -> {remote_sha[:7]}). Triggering deploy..."
                    )
                    state.last_remote_commits[proj_id] = remote_sha
                    trigger_deploy(
                        project=project,
                        trigger_type="polling",
                        author="Git Polling",
                        commit_msg=f"Detected new commit {remote_sha[:7]} on {remote}/{branch}",
                        telegram_config=tg_config
                    )
        except Exception as exc:
            logging.error(f"Error in polling worker: {exc}")

        # Sleep briefly between poll scans
        time.sleep(2)

def write_pid() -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

def remove_pid() -> None:
    try:
        PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass

def run_engine() -> None:
    """Main entrypoint for the headless engine."""
    setup_logging()
    logging.info("=" * 60)
    logging.info("Starting AutoDeploy Engine (Headless)")
    logging.info(f"Process PID: {os.getpid()}")
    logging.info("=" * 60)

    write_pid()

    # Initial config load
    initial_config = load_config()
    state.config = initial_config
    state.config_mtime = get_config_mtime()

    server_cfg = initial_config.get("server", {})
    host = server_cfg.get("host", "0.0.0.0")
    port = int(server_cfg.get("port", 9876))

    def handle_exit(signum: Any, frame: Any) -> None:
        logging.info(f"Signal {signum} received. Stopping AutoDeploy Engine...")
        state.is_running = False
        if state.server:
            threading.Thread(target=state.server.shutdown).start()
        remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Start watcher and polling threads
    watcher = threading.Thread(target=config_watcher_thread, daemon=True, name="config-watcher")
    watcher.start()

    poller = threading.Thread(target=polling_worker_thread, daemon=True, name="git-poller")
    poller.start()

    # Start HTTP Webhook server
    try:
        server = http.server.ThreadingHTTPServer((host, port), WebhookRequestHandler)
        state.server = server
        logging.info(f"AutoDeploy Webhook HTTP Server listening on http://{host}:{port}")
        server.serve_forever()
    except Exception as exc:
        logging.error(f"Fatal HTTP server error: {exc}")
    finally:
        state.is_running = False
        remove_pid()
        logging.info("AutoDeploy Engine terminated.")
