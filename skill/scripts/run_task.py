#!/usr/bin/env python3
"""run_task.py - 执行器抽象层。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from platform_utils import default_python, terminate_process_tree
from run_store import (
    read_run_record,
    simple_run_status,
    stop_task,
    stop_run_record,
    update_run_status,
    write_run_record,
)
from tasks_store import CliError


LOGS_DIR = Path(".dual-ai-collab/logs")
BACKENDS = ("direct", "plugin")
_WORKER_CHILD: subprocess.Popen | None = None


def _make_run_id(task_num: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"task-{task_num}-{ts}"


def _start_direct(task_num: str, prompt: str, workdir: str) -> dict:
    log_file = LOGS_DIR / f"task-{task_num}.log"
    exit_file = LOGS_DIR / f"task-{task_num}.exit"
    pid_file = LOGS_DIR / f"task-{task_num}.pid"

    log_file.parent.mkdir(parents=True, exist_ok=True)
    exit_file.unlink(missing_ok=True)

    worker_cmd = [
        default_python(),
        str(Path(__file__).resolve()),
        "_worker",
        task_num,
        prompt,
        "--workdir",
        workdir,
        "--log-file",
        str(log_file),
        "--exit-file",
        str(exit_file),
    ]

    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(worker_cmd, **popen_kwargs)
    except OSError as exc:
        raise CliError(f"无法启动后台 worker: {exc}") from exc

    pid_file.write_text(f"{proc.pid}\n", encoding="utf-8")

    record = {
        "run_id": _make_run_id(task_num),
        "task_num": task_num,
        "backend": "direct",
        "pid": proc.pid,
        "log_file": str(log_file),
        "exit_file": str(exit_file),
        "pid_file": str(pid_file),
        "workdir": workdir,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "running",
    }
    write_run_record(record)
    return record


def _start_plugin(task_num: str, prompt: str, workdir: str) -> dict:
    raise CliError("plugin backend 尚未实现；当前请使用 --backend direct")


def _status_direct(record: dict) -> dict:
    return update_run_status(record)


def _status_plugin(record: dict) -> dict:
    raise CliError("plugin backend 尚未实现")


def _stop_direct(record: dict) -> dict:
    return stop_run_record(record)


def _stop_plugin(record: dict) -> dict:
    raise CliError("plugin backend 尚未实现")


_BACKEND_DISPATCH = {
    "direct": {"start": _start_direct, "status": _status_direct, "stop": _stop_direct},
    "plugin": {"start": _start_plugin, "status": _status_plugin, "stop": _stop_plugin},
}


def cmd_worker(task_num: str, prompt: str, workdir: str, log_file: str, exit_file: str) -> None:
    global _WORKER_CHILD
    log_path = Path(log_file)
    exit_path = Path(exit_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.unlink(missing_ok=True)

    def _handle_signal(_signum, _frame):
        if _WORKER_CHILD is not None and _WORKER_CHILD.poll() is None:
            terminate_process_tree(_WORKER_CHILD.pid, force=True)
        exit_path.write_text("143\n", encoding="utf-8")
        raise SystemExit(143)

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handle_signal)

    with open(log_path, "w", encoding="utf-8") as log_handle:
        child_kwargs = {
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            child_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            child_kwargs["start_new_session"] = True

        try:
            _WORKER_CHILD = subprocess.Popen(
                ["codex", "exec", "-C", workdir, "--full-auto", prompt],
                **child_kwargs,
            )
        except OSError as exc:
            log_handle.write(f"ERROR: 无法启动 codex: {exc}\n")
            exit_path.write_text("127\n", encoding="utf-8")
            raise SystemExit(127)

        exit_code = _WORKER_CHILD.wait()

    exit_path.write_text(f"{exit_code}\n", encoding="utf-8")


def cmd_start(task_num: str, prompt: str, backend: str, workdir: str) -> int:
    if backend not in BACKENDS:
        raise CliError(f"不支持的 backend: {backend}，可选: {', '.join(BACKENDS)}")
    record = _BACKEND_DISPATCH[backend]["start"](task_num, prompt, workdir)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_status(task_num: str) -> int:
    record = read_run_record(task_num)
    if not record:
        print(simple_run_status(task_num))
        return 0
    backend = record.get("backend", "direct")
    result = _BACKEND_DISPATCH[backend]["status"](record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_stop(task_num: str) -> int:
    record = read_run_record(task_num)
    if not record:
        result = stop_task(task_num)
        print(result["status"] if result else "not_found")
        return 0

    if record.get("status") != "running":
        print(f"SKIP: 任务 #{task_num} 当前状态为 {record.get('status')}，无需终止")
        return 0

    backend = record.get("backend", "direct")
    result = _BACKEND_DISPATCH[backend]["stop"](record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def register_subparsers(subparsers, *, nested: bool = False):
    if nested:
        run_parser = subparsers.add_parser("run", help="任务执行器")
        run_sub = run_parser.add_subparsers(dest="run_command")

        p_start = run_sub.add_parser("start", help="启动任务执行")
        p_start.add_argument("task_num")
        p_start.add_argument("prompt")
        p_start.add_argument("--backend", default="direct", choices=BACKENDS)
        p_start.add_argument("--workdir", default=None)

        p_status = run_sub.add_parser("status", help="查询运行状态")
        p_status.add_argument("task_num")

        p_stop = run_sub.add_parser("stop", help="终止运行中的任务")
        p_stop.add_argument("task_num")
        return run_parser

    p_start = subparsers.add_parser("start", help="启动任务执行")
    p_start.add_argument("task_num")
    p_start.add_argument("prompt")
    p_start.add_argument("--backend", default="direct", choices=BACKENDS)
    p_start.add_argument("--workdir", default=None)

    p_status = subparsers.add_parser("status", help="查询运行状态")
    p_status.add_argument("task_num")

    p_stop = subparsers.add_parser("stop", help="终止运行中的任务")
    p_stop.add_argument("task_num")

    p_worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    p_worker.add_argument("task_num")
    p_worker.add_argument("prompt")
    p_worker.add_argument("--workdir", required=True)
    p_worker.add_argument("--log-file", required=True)
    p_worker.add_argument("--exit-file", required=True)
    return None


def dispatch(args) -> int:
    if getattr(args, "command", None) == "_worker":
        cmd_worker(args.task_num, args.prompt, args.workdir, args.log_file, args.exit_file)
        return 0

    if getattr(args, "run_command", None) == "start" or getattr(args, "command", None) == "start":
        workdir = args.workdir or os.getcwd()
        return cmd_start(args.task_num, args.prompt, args.backend, workdir)
    if getattr(args, "run_command", None) == "status" or getattr(args, "command", None) == "status":
        return cmd_status(args.task_num)
    if getattr(args, "run_command", None) == "stop" or getattr(args, "command", None) == "stop":
        return cmd_stop(args.task_num)
    raise CliError("缺少有效的 run 子命令")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="执行器抽象层")
    register_subparsers(parser.add_subparsers(dest="command"), nested=False)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(dispatch(args))
    except CliError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
