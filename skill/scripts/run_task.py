#!/usr/bin/env python3
"""run_task.py - 执行器抽象层

将 codex exec 启动逻辑从 skill 文档下沉到脚本，
产出统一的 run record，为 direct/plugin 双 backend 留接口。

子命令:
  start   启动任务执行
  status  查询运行状态
  stop    终止运行中的任务
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# 常量与路径
# ═══════════════════════════════════════════════════════════════════════════════

LOGS_DIR = Path(".dual-ai-collab/logs")
RUNS_DIR = Path(".dual-ai-collab/runs")

# 支持的 backend 类型
BACKENDS = ("direct", "plugin")


# ═══════════════════════════════════════════════════════════════════════════════
# Run Record — 统一执行结果契约
# ═══════════════════════════════════════════════════════════════════════════════


def _run_record_path(task_num: str) -> Path:
    return RUNS_DIR / f"task-{task_num}.json"


def _read_run_record(task_num: str) -> dict:
    path = _run_record_path(task_num)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_run_record(record: dict) -> None:
    path = _run_record_path(record["task_num"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _make_run_id(task_num: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"task-{task_num}-{ts}"


# ═══════════════════════════════════════════════════════════════════════════════
# Backend: direct (codex exec via bash)
# ═══════════════════════════════════════════════════════════════════════════════


def _start_direct(task_num: str, prompt: str, workdir: str) -> dict:
    """启动 codex exec 后台进程，返回 run record。"""
    log_file = LOGS_DIR / f"task-{task_num}.log"
    exit_file = LOGS_DIR / f"task-{task_num}.exit"
    pid_file = LOGS_DIR / f"task-{task_num}.pid"

    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 构建 shell 命令：(codex exec ... > log 2>&1; echo $? > exit_file) &
    shell_cmd = (
        f'( codex exec -C "{workdir}" --full-auto {_shell_quote(prompt)}'
        f' > {_shell_quote(str(log_file))} 2>&1;'
        f' echo $? > {_shell_quote(str(exit_file))} ) &'
        f' echo $!'
    )

    result = subprocess.run(
        ["bash", "-c", shell_cmd],
        capture_output=True, text=True, timeout=10,
    )

    pid_str = result.stdout.strip()
    if not pid_str.isdigit():
        print(f"ERROR: 无法启动 codex exec，输出: {result.stdout} {result.stderr}",
              file=sys.stderr)
        sys.exit(1)

    pid = int(pid_str)

    # 写 PID 文件（供 detect_stall 兼容）
    pid_file.write_text(f"{pid}\n")

    run_id = _make_run_id(task_num)
    record = {
        "run_id": run_id,
        "task_num": task_num,
        "backend": "direct",
        "pid": pid,
        "log_file": str(log_file),
        "exit_file": str(exit_file),
        "pid_file": str(pid_file),
        "workdir": workdir,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "running",
    }

    _write_run_record(record)
    return record


def _status_direct(record: dict) -> dict:
    """查询 direct backend 的运行状态。"""
    pid = record.get("pid", 0)
    exit_file = Path(record.get("exit_file", ""))

    # 检查进程是否存活
    alive = False
    if pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except (OSError, ProcessLookupError):
            pass

    if alive:
        record["status"] = "running"
    else:
        # 进程已退出，读取退出码
        exit_code = None
        if exit_file.exists():
            try:
                exit_code = int(exit_file.read_text().strip())
            except (ValueError, OSError):
                exit_code = 1
        else:
            exit_code = 1

        record["exit_code"] = exit_code
        record["status"] = "success" if exit_code == 0 else "failed"
        record["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_run_record(record)

    return record


def _stop_direct(record: dict) -> dict:
    """终止 direct backend 的运行进程。"""
    pid = record.get("pid", 0)
    if pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
            # 等待最多 5 秒
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except (OSError, ProcessLookupError):
                    break
            else:
                # 仍在运行，强制 kill
                try:
                    os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        except (OSError, ProcessLookupError):
            pass

    record["status"] = "stopped"
    record["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_run_record(record)
    return record


# ═══════════════════════════════════════════════════════════════════════════════
# Backend: plugin (预留接口)
# ═══════════════════════════════════════════════════════════════════════════════


def _start_plugin(task_num: str, prompt: str, workdir: str) -> dict:
    """plugin backend 启动（预留接口）。"""
    print("ERROR: plugin backend 尚未实现", file=sys.stderr)
    print("提示: 当前可使用 --backend direct（默认）", file=sys.stderr)
    sys.exit(1)


def _status_plugin(record: dict) -> dict:
    """plugin backend 状态查询（预留接口）。"""
    print("ERROR: plugin backend 尚未实现", file=sys.stderr)
    sys.exit(1)


def _stop_plugin(record: dict) -> dict:
    """plugin backend 终止（预留接口）。"""
    print("ERROR: plugin backend 尚未实现", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# Backend 分发
# ═══════════════════════════════════════════════════════════════════════════════

_BACKEND_DISPATCH = {
    "direct": {
        "start": _start_direct,
        "status": _status_direct,
        "stop": _stop_direct,
    },
    "plugin": {
        "start": _start_plugin,
        "status": _status_plugin,
        "stop": _stop_plugin,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def _shell_quote(s: str) -> str:
    """安全的 shell 引号转义。"""
    return "'" + s.replace("'", "'\\''") + "'"


# ═══════════════════════════════════════════════════════════════════════════════
# 子命令
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_start(task_num: str, prompt: str, backend: str, workdir: str):
    """启动任务执行。"""
    if backend not in BACKENDS:
        print(f"ERROR: 不支持的 backend: {backend}，可选: {', '.join(BACKENDS)}",
              file=sys.stderr)
        sys.exit(1)

    start_fn = _BACKEND_DISPATCH[backend]["start"]
    record = start_fn(task_num, prompt, workdir)

    # 输出 JSON，供调用方解析
    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_status(task_num: str):
    """查询任务运行状态。"""
    record = _read_run_record(task_num)
    if not record:
        print(json.dumps({"task_num": task_num, "status": "not_found"}, ensure_ascii=False))
        return

    backend = record.get("backend", "direct")
    status_fn = _BACKEND_DISPATCH[backend]["status"]
    record = status_fn(record)

    print(json.dumps(record, ensure_ascii=False, indent=2))


def cmd_stop(task_num: str):
    """终止运行中的任务。"""
    record = _read_run_record(task_num)
    if not record:
        print(f"ERROR: 未找到任务 #{task_num} 的运行记录", file=sys.stderr)
        sys.exit(1)

    if record.get("status") not in ("running",):
        print(f"SKIP: 任务 #{task_num} 当前状态为 {record.get('status')}，无需终止")
        return

    backend = record.get("backend", "direct")
    stop_fn = _BACKEND_DISPATCH[backend]["stop"]
    record = stop_fn(record)

    print(json.dumps(record, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="执行器抽象层")
    sub = parser.add_subparsers(dest="command")

    # start
    p_start = sub.add_parser("start", help="启动任务执行")
    p_start.add_argument("task_num", help="任务编号")
    p_start.add_argument("prompt", help="执行提示词")
    p_start.add_argument("--backend", default="direct", choices=BACKENDS,
                         help="执行后端 (默认: direct)")
    p_start.add_argument("--workdir", default=None,
                         help="工作目录 (默认: 当前目录)")

    # status
    p_status = sub.add_parser("status", help="查询运行状态")
    p_status.add_argument("task_num", help="任务编号")

    # stop
    p_stop = sub.add_parser("stop", help="终止运行中的任务")
    p_stop.add_argument("task_num", help="任务编号")

    args = parser.parse_args()

    if args.command == "start":
        workdir = args.workdir or os.getcwd()
        cmd_start(args.task_num, args.prompt, args.backend, workdir)
    elif args.command == "status":
        cmd_status(args.task_num)
    elif args.command == "stop":
        cmd_stop(args.task_num)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
