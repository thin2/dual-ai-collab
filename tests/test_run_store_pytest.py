from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from run_store import read_run_record, simple_run_status, stop_task, update_run_status, write_run_record  # noqa: E402


def test_update_run_status_marks_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".dual-ai-collab/logs").mkdir(parents=True)
    Path(".dual-ai-collab/runs").mkdir(parents=True)
    Path(".dual-ai-collab/logs/task-001.exit").write_text("0\n", encoding="utf-8")

    record = {"task_num": "001", "backend": "direct", "pid": 999999, "status": "running"}
    write_run_record(record)

    updated = update_run_status(read_run_record("001"))
    assert updated["status"] == "success"
    assert updated["exit_code"] == 0


def test_simple_run_status_reports_running(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".dual-ai-collab/logs").mkdir(parents=True)

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        Path(".dual-ai-collab/logs/task-002.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
        assert simple_run_status("002") == "running"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_stop_task_terminates_process(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".dual-ai-collab/logs").mkdir(parents=True)

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        Path(".dual-ai-collab/logs/task-003.pid").write_text(f"{proc.pid}\n", encoding="utf-8")
        result = stop_task("003")
        assert result is not None
        assert result["status"] == "stopped"
        time.sleep(0.2)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
