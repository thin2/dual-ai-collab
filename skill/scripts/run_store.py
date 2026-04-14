#!/usr/bin/env python3
"""运行记录与进程状态的共享逻辑。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tasks_store import CliError, atomic_write
from platform_utils import is_process_running, terminate_process_tree, wait_for_process_exit


RUNS_DIR = Path(".dual-ai-collab/runs")
LOGS_DIR = Path(".dual-ai-collab/logs")


def run_record_path(task_num: str) -> Path:
    return RUNS_DIR / f"task-{task_num}.json"


def pid_file_path(task_num: str) -> Path:
    return LOGS_DIR / f"task-{task_num}.pid"


def exit_file_path(task_num: str) -> Path:
    return LOGS_DIR / f"task-{task_num}.exit"


def read_run_record(task_num: str) -> dict:
    path = run_record_path(task_num)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def write_run_record(record: dict) -> None:
    path = run_record_path(record["task_num"])
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def read_task_pid(task_num: str) -> int | None:
    pid_file = pid_file_path(task_num)
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_exit_code(task_num: str) -> int | None:
    exit_file = exit_file_path(task_num)
    if not exit_file.exists():
        return None
    try:
        return int(exit_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 1


def update_run_status(record: dict) -> dict:
    pid = int(record.get("pid", 0) or 0)
    if pid > 0 and is_process_running(pid):
        record["status"] = "running"
        return record

    exit_code = read_exit_code(record["task_num"])
    if exit_code is None:
        exit_code = 1

    record["exit_code"] = exit_code
    record["status"] = "success" if exit_code == 0 else "failed"
    record["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_run_record(record)
    return record


def stop_run_record(record: dict) -> dict:
    pid = int(record.get("pid", 0) or 0)
    if pid > 0 and is_process_running(pid):
        terminate_process_tree(pid, force=False)
        if not wait_for_process_exit(pid, timeout_sec=5):
            terminate_process_tree(pid, force=True)

    pid_file_path(record["task_num"]).unlink(missing_ok=True)
    record["status"] = "stopped"
    record["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_run_record(record)
    return record


def simple_run_status(task_num: str) -> str:
    record = read_run_record(task_num)
    if record:
        return update_run_status(record).get("status", "not_found")

    pid = read_task_pid(task_num)
    if pid is not None and is_process_running(pid):
        return "running"

    exit_code = read_exit_code(task_num)
    if exit_code is not None:
        return "success" if exit_code == 0 else "failed"

    if pid_file_path(task_num).exists():
        return "stopped"
    return "not_found"


def stop_task(task_num: str) -> dict | None:
    record = read_run_record(task_num)
    if record:
        return stop_run_record(record)

    pid_file = pid_file_path(task_num)
    pid = read_task_pid(task_num)
    if pid is None:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
            return {"task_num": task_num, "status": "stopped"}
        return None

    if is_process_running(pid):
        terminate_process_tree(pid, force=False)
        if not wait_for_process_exit(pid, timeout_sec=5):
            terminate_process_tree(pid, force=True)

    pid_file.unlink(missing_ok=True)
    return {"task_num": task_num, "status": "stopped"}


def require_running_record(task_num: str) -> dict:
    record = read_run_record(task_num)
    if not record:
        raise CliError(f"未找到任务 #{task_num} 的运行记录")
    return record
