"""
Background worker threads for PySide6 UI to guarantee zero interface freezing.
Handles Git tests, Telegram test notifications, manual deploys, and Engine status polling.
"""

import json
import urllib.request
from typing import Any, Dict, Optional
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core.deployer import (
    git_get_head_commit,
    git_get_remote_commit,
    trigger_deploy,
)
from core.service_ctl import get_engine_status
from core.telegram import send_telegram_notification

class GitTestSignals(QObject):
    finished = Signal(bool, str, str)  # success, local_sha, remote_sha_or_error

class GitTestWorker(QRunnable):
    def __init__(self, repo_path: str, remote: str = "origin", branch: str = "main"):
        super().__init__()
        self.repo_path = repo_path
        self.remote = remote
        self.branch = branch
        self.signals = GitTestSignals()

    def run(self) -> None:
        try:
            local_sha = git_get_head_commit(self.repo_path)
            if not local_sha:
                self.signals.finished.emit(False, "", f"Directory '{self.repo_path}' is not a valid git repository or HEAD is uninitialized.")
                return

            remote_sha = git_get_remote_commit(self.repo_path, self.remote, self.branch)
            if not remote_sha:
                self.signals.finished.emit(False, local_sha, f"Could not reach remote '{self.remote}/{self.branch}'")
                return

            self.signals.finished.emit(True, local_sha, remote_sha)
        except Exception as exc:
            self.signals.finished.emit(False, "", str(exc))

class TelegramTestSignals(QObject):
    finished = Signal(bool, str)

class TelegramTestWorker(QRunnable):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.signals = TelegramTestSignals()

    def run(self) -> None:
        msg = "<b>[AutoDeploy]</b> Test notification from Windows Server GUI. Setup is working properly!"
        success, err = send_telegram_notification(self.bot_token, self.chat_id, msg)
        self.signals.finished.emit(success, err)

class DeploySignals(QObject):
    finished = Signal(bool, str)

class ManualDeployWorker(QRunnable):
    def __init__(self, project: Dict[str, Any], telegram_cfg: Optional[Dict[str, Any]] = None, engine_port: int = 9876):
        super().__init__()
        self.project = project
        self.telegram_cfg = telegram_cfg
        self.engine_port = engine_port
        self.signals = DeploySignals()

    def run(self) -> None:
        proj_id = self.project.get("id", "")
        # If engine is running, prefer notifying the engine via HTTP /api/deploy/<id>
        is_running, _ = get_engine_status()
        if is_running:
            try:
                url = f"http://127.0.0.1:{self.engine_port}/api/deploy/{proj_id}"
                req = urllib.request.Request(url, method="POST", data=b"{}")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        self.signals.finished.emit(True, data.get("message", "Deploy triggered via Engine"))
                        return
            except Exception:
                pass  # Fallback to direct thread deploy

        # Direct deploy fallback (e.g. if engine is not running)
        success, msg = trigger_deploy(
            project=self.project,
            trigger_type="manual",
            author="GUI User",
            commit_msg="Manual deploy triggered via PySide6 GUI",
            telegram_config=self.telegram_cfg
        )
        self.signals.finished.emit(success, msg)
