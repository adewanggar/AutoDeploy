"""
Telegram notification dispatcher for AutoDeploy using standard library urllib.
"""

import json
import urllib.request
import urllib.error
from typing import Tuple

def send_telegram_notification(bot_token: str, chat_id: str, message: str, parse_mode: str = "HTML") -> Tuple[bool, str]:
    """Sends a notification message to a Telegram chat via Telegram Bot API."""
    if not bot_token or not chat_id:
        return False, "Bot token or chat ID is empty"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return True, "Message sent successfully"
            return False, f"Unexpected HTTP status {response.status}"
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="replace")
        return False, f"Telegram API error {err.code}: {err_msg}"
    except Exception as exc:
        return False, f"Telegram error: {str(exc)}"

def format_deploy_notification(
    project_name: str,
    status: str,
    duration: float,
    trigger: str,
    old_commit: str,
    new_commit: str,
    commit_msg: str,
    author: str,
    error_detail: str = ""
) -> str:
    """Formats deployment outcome into a concise, readable HTML message."""
    status_label = {
        "success": "SUCCESS",
        "failed": "FAILED",
        "rolled_back": "ROLLED BACK"
    }.get(status, status.upper())
    
    short_old = old_commit[:7] if old_commit else "N/A"
    short_new = new_commit[:7] if new_commit else "N/A"
    
    lines = [
        f"<b>[AutoDeploy] {project_name}</b>",
        f"Status: <b>{status_label}</b>",
        f"Trigger: {trigger} | Duration: {duration:.1f}s",
        f"Commit: <code>{short_old}</code> -> <code>{short_new}</code>",
    ]
    if author:
        lines.append(f"Author: {author}")
    if commit_msg:
        first_line = commit_msg.strip().split("\n")[0]
        lines.append(f"Message: {first_line}")
    if error_detail and status in ("failed", "rolled_back"):
        lines.append(f"\n<b>Failure Reason:</b>\n<pre>{error_detail[:500]}</pre>")
    
    return "\n".join(lines)
