"""
Self-check tests for AutoDeploy core logic.
Uses standard library assert only (no pytest/framework bloat).
"""

import hmac
import hashlib
import json
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import DEFAULT_CONFIG, load_config, save_config, create_default_project
from core.history import append_history, load_history, MAX_HISTORY_ENTRIES
from core.deployer import run_shell_command
from core.service_ctl import is_pid_alive
import os

def test_config():
    cfg = load_config()
    assert "server" in cfg
    assert "projects" in cfg
    proj = create_default_project("test-app", "Test App")
    assert proj["id"] == "test-app"
    assert proj["branch"] == "main"
    print("[PASS] Config self-check")

def test_hmac_signature():
    secret = "my-webhook-secret"
    payload = b'{"ref": "refs/heads/main"}'
    expected_hex = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    header = f"sha256={expected_hex}"
    
    # Matching check
    sig_val = header.split("sha256=")[-1]
    assert hmac.compare_digest(expected_hex, sig_val)
    
    # Tampered check
    tampered_payload = b'{"ref": "refs/heads/dev"}'
    wrong_sig = hmac.new(secret.encode("utf-8"), tampered_payload, hashlib.sha256).hexdigest()
    assert not hmac.compare_digest(wrong_sig, sig_val)
    print("[PASS] HMAC signature self-check")

def test_shell_command():
    code, out, dur = run_shell_command("echo AutoDeployWorks", cwd=os.getcwd(), shell_type="cmd")
    assert code == 0
    assert "AutoDeployWorks" in out
    print("[PASS] Shell command execution self-check")

def test_history():
    entry = {
        "id": f"test-{int(time.time()*1000)}",
        "project_id": "test-app",
        "project_name": "Test App",
        "timestamp": "2026-09-24T10:00:00",
        "duration_seconds": 1.2,
        "trigger": "manual",
        "status": "success",
        "old_commit": "aaaa111",
        "new_commit": "bbbb222",
        "author": "tester",
        "commit_message": "test commit",
        "steps_log": []
    }
    append_history(entry)
    hist = load_history(10)
    assert len(hist) > 0
    assert hist[0]["project_id"] == "test-app"
    print("[PASS] History JSONL self-check")

if __name__ == "__main__":
    test_config()
    test_hmac_signature()
    test_shell_command()
    test_history()
    print("All core self-tests passed successfully!")
