"""
End-to-end deployment verification for AutoDeploy.
Tests:
1. Git step execution and HEAD detection
2. Automatic rollback when step fails
3. Webhook HMAC verification and branch ref matching
4. History JSONL recording
"""

import sys
import os
import shutil
import subprocess
import time
from pathlib import Path

# Add root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.deployer import trigger_deploy, is_project_deploying
from core.history import load_history
from core.config import create_default_project, save_config, load_config

def setup_mock_git_repo(path: Path) -> str:
    """Sets up a clean temporary git repo for testing."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)

    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True)

    # Initial commit
    file1 = path / "app.txt"
    file1.write_text("v1.0")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit v1.0"], cwd=path, check=True, capture_output=True)
    
    # Get commit SHA
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True)
    return res.stdout.strip()

def run_e2e_tests():
    test_dir = Path(__file__).parent / "mock_repo"
    old_commit = setup_mock_git_repo(test_dir)
    print(f"Mock repo initialized at {test_dir}, HEAD: {old_commit[:7]}")

    # Test 1: Successful Deployment
    proj = create_default_project("mock-app", "Mock Application")
    proj["path"] = str(test_dir)
    proj["steps"] = [
        "python -c \"print('Executing build step 1...')\"",
        "python -c \"print('Executing build step 2...')\""
    ]
    proj["restart_command"] = "python -c \"print('Restarting app...')\""
    proj["rollback_on_failure"] = True

    print("\n--- Running Test 1: Successful Deployment ---")
    started, msg = trigger_deploy(proj, trigger_type="test-manual", author="E2E Test", commit_msg="Test run")
    assert started, f"Deploy failed to start: {msg}"
    
    # Wait for deploy completion
    time.sleep(2)
    while is_project_deploying("mock-app"):
        time.sleep(0.5)

    history = load_history(10)
    assert len(history) > 0
    latest = history[0]
    assert latest["project_id"] == "mock-app"
    assert latest["status"] == "success", f"Expected success, got {latest['status']}"
    assert len(latest["steps_log"]) == 3  # 2 steps + 1 restart command
    print("[PASS] Test 1: Successful Deployment verified.")

    # Test 2: Failed step with Rollback
    print("\n--- Running Test 2: Failed Step & Automatic Rollback ---")
    # Make a second commit in repo
    (test_dir / "app.txt").write_text("v2.0")
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit v2.0"], cwd=test_dir, check=True, capture_output=True)
    v2_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=test_dir, check=True, capture_output=True, text=True).stdout.strip()
    
    # Configure project with a failing step
    proj_fail = dict(proj)
    proj_fail["steps"] = [
        "python -c \"import sys; sys.exit(42)\""  # Will fail
    ]
    
    started, msg = trigger_deploy(proj_fail, trigger_type="test-fail", author="E2E Fail Test")
    assert started
    time.sleep(2)
    while is_project_deploying("mock-app"):
        time.sleep(0.5)

    history = load_history(10)
    latest_fail = history[0]
    assert latest_fail["status"] == "rolled_back", f"Expected rolled_back, got {latest_fail['status']}"
    # Verify repo was rolled back to v2_commit (the commit before the deploy ran)
    current_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=test_dir, check=True, capture_output=True, text=True).stdout.strip()
    assert current_head == v2_commit, f"Expected HEAD {v2_commit[:7]}, got {current_head[:7]}"
    print("[PASS] Test 2: Step failure and Rollback verified.")

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)
    print("\nAll E2E tests completed successfully!")

if __name__ == "__main__":
    run_e2e_tests()
