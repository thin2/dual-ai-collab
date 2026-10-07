"""Test error handling improvements."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import run_task
from run_store import read_run_record


FAILING_CODEX = """#!/usr/bin/env python3
import sys
sys.stderr.write("ERROR: Something went wrong\\n")
sys.stderr.write("Traceback line 1\\n")
sys.stderr.write("Traceback line 2\\n")
sys.exit(1)
"""


@pytest.mark.skipif(os.name == "nt", reason="stub codex 使用 shebang 脚本")
def test_error_details_captured_on_failure(tmp_path, monkeypatch):
    """Verify error details are captured when worker fails."""
    monkeypatch.chdir(tmp_path)

    # Create failing stub codex
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "codex"
    stub.write_text(FAILING_CODEX, encoding="utf-8")
    stub.chmod(0o755)

    monkeypatch.setenv("CODEX_BIN", str(stub))

    # Start task
    run_task.cmd_start("999", "test prompt", "direct", str(tmp_path))

    # Wait for completion
    deadline = time.time() + 10
    while time.time() < deadline:
        record = read_run_record("999")
        status = run_task._status_direct(record)
        if status["status"] != "running":
            break
        time.sleep(0.1)

    # Verify failure captured
    assert status["status"] == "failed"
    assert status["exit_code"] == 1

    # Verify error details exist
    assert "error_details" in status
    error_details = status["error_details"]
    assert error_details["error"] == "non_zero_exit"
    assert error_details["exit_code"] == 1
    assert "duration_seconds" in error_details
    assert error_details["duration_seconds"] > 0

    # Verify log tail captured
    assert "log_tail" in error_details
    log_tail = "\n".join(error_details["log_tail"])
    assert "ERROR: Something went wrong" in log_tail


@pytest.mark.skipif(os.name == "nt", reason="Unix signal handling")
def test_error_details_on_signal_termination(tmp_path, monkeypatch):
    """Verify error details captured on signal termination."""
    monkeypatch.chdir(tmp_path)

    # Create long-running stub
    stub_script = """#!/usr/bin/env python3
import time
print("Started", flush=True)
time.sleep(60)
"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "codex"
    stub.write_text(stub_script, encoding="utf-8")
    stub.chmod(0o755)

    monkeypatch.setenv("CODEX_BIN", str(stub))

    # Start task
    run_task.cmd_start("998", "test prompt", "direct", str(tmp_path))

    # Wait for it to start
    time.sleep(0.5)

    # Stop it
    run_task.cmd_stop("998")

    # Wait for termination
    time.sleep(0.5)

    # Check status
    record = read_run_record("998")
    assert record["status"] == "stopped"

    # Check error file exists
    log_file = Path(record["log_file"])
    error_file = log_file.with_suffix(".error.json")
    assert error_file.exists()

    error_data = json.loads(error_file.read_text(encoding="utf-8"))
    assert error_data["error"] == "terminated_by_signal"
    assert "signal" in error_data
