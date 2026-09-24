"""
End-to-end Webhook HTTP test for AutoDeploy.
Starts engine in thread, sends ping, invalid signature, valid signature, and branch filtering.
"""

import hashlib
import hmac
import http.client
import json
import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.engine import state, WebhookRequestHandler
import http.server

def run_webhook_test():
    host = "127.0.0.1"
    port = 9877

    # Configure a test project in state
    secret = "my-secret-key"
    test_project = {
        "id": "e2e-project",
        "name": "E2E Webhook App",
        "enabled": True,
        "path": r"C:\apps\dummy",
        "remote": "origin",
        "branch": "production",
        "trigger_mode": "webhook",
        "secret": secret,
        "steps": [],
        "restart_command": ""
    }
    state.config = {
        "server": {"host": host, "port": port},
        "projects": [test_project]
    }

    server = http.server.ThreadingHTTPServer((host, port), WebhookRequestHandler)
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()
    time.sleep(0.5)

    try:
        # Test 1: GET /health
        conn = http.client.HTTPConnection(host, port)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        assert resp.status == 200
        health_data = json.loads(resp.read().decode())
        assert health_data["status"] == "ok"
        print("[PASS] GET /health returned 200 OK")

        # Test 2: Webhook without signature -> 403
        conn.request("POST", "/hook/e2e-project", body=b"{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 403
        print("[PASS] Webhook without signature returned 403 Forbidden")

        # Test 3: Webhook with invalid signature -> 403
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=wrongsignature1234567890abcdef"
        }
        conn.request("POST", "/hook/e2e-project", body=b"{}", headers=headers)
        resp = conn.getresponse()
        assert resp.status == 403
        print("[PASS] Webhook with invalid signature returned 403 Forbidden")

        # Test 4: Webhook with valid signature, ping event -> 200
        ping_body = json.dumps({"zen": "Keep it simple"}).encode()
        sig = "sha256=" + hmac.new(secret.encode(), ping_body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "ping"
        }
        conn.request("POST", "/hook/e2e-project", body=ping_body, headers=headers)
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data.get("status") == "pong"
        print("[PASS] Webhook GitHub ping event returned 200 pong")

        # Test 5: Webhook with push event to non-matching branch -> 200 (ref_ignored)
        push_dev_body = json.dumps({"ref": "refs/heads/development"}).encode()
        sig_dev = "sha256=" + hmac.new(secret.encode(), push_dev_body, hashlib.sha256).hexdigest()
        headers["X-GitHub-Event"] = "push"
        headers["X-Hub-Signature-256"] = sig_dev
        conn.request("POST", "/hook/e2e-project", body=push_dev_body, headers=headers)
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data.get("status") == "ref_ignored"
        print("[PASS] Push event on development branch ignored (branch mismatch)")

        # Test 6: Body > 1MB rejected -> 413
        large_body = b"x" * (1024 * 1024 + 10)
        conn.request("POST", "/hook/e2e-project", body=large_body, headers={"Content-Length": str(len(large_body))})
        resp = conn.getresponse()
        assert resp.status == 413
        print("[PASS] Webhook with payload > 1MB returned 413 Payload Too Large")

        print("\nAll Webhook E2E tests passed successfully!")
    finally:
        server.shutdown()

if __name__ == "__main__":
    run_webhook_test()
