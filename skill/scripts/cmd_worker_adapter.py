#!/usr/bin/env python3
"""Adapter worker - 通过自定义 CLI 适配器执行任务。"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from platform_utils import terminate_process_tree
from structured_logging import log_event, log_metric, log_span_start, log_span_end


_WORKER_CHILD: subprocess.Popen | None = None


def cmd_worker_adapter(
    task_num: str,
    prompt_file: str,
    workdir: str,
    log_file: str,
    exit_file: str,
    adapter_name: str,
    adapter_cmd: list[str],
    *,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    schema_file: str | None = None,
    result_file: str | None = None,
) -> None:
    """使用 adapter CLI 执行任务的 worker 进程。"""
    global _WORKER_CHILD
    os.chdir(workdir)

    span_ctx = log_span_start("worker_adapter_execution",
                              task_num=task_num, adapter=adapter_name)

    log_path = Path(log_file)
    exit_path = Path(exit_file)
    error_path = Path(log_file).with_suffix(".error.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.unlink(missing_ok=True)
    error_path.unlink(missing_ok=True)

    def _handle_signal(_signum, _frame):
        if _WORKER_CHILD is not None and _WORKER_CHILD.poll() is None:
            terminate_process_tree(_WORKER_CHILD.pid, force=True)
        exit_path.write_text("143\n", encoding="utf-8")
        error_path.write_text(
            json.dumps({"error": "terminated_by_signal", "signal": _signum},
                      ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        log_span_end(span_ctx, success=False, reason="terminated_by_signal", signal=_signum)
        raise SystemExit(143)

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handle_signal)

    # 构建 adapter 命令
    cmd = adapter_cmd.copy()

    # 处理命令中的占位符或追加参数
    prompt_via_stdin = True
    if "{prompt}" in cmd:
        # 占位符模式：直接替换
        prompt_text = Path(prompt_file).read_text(encoding="utf-8")
        cmd = [arg.replace("{prompt}", prompt_text) if arg == "{prompt}" else arg
               for arg in cmd]
        prompt_via_stdin = False

    # 添加可选参数
    if model and "--model" not in cmd and "-m" not in cmd:
        cmd += ["-m", model]

    if effort and "--effort" not in cmd:
        # 将 effort 映射到 model_reasoning_effort 配置
        cmd += ["-c", f"model_reasoning_effort={effort}"]

    if sandbox and "--sandbox" not in cmd and "-s" not in cmd:
        cmd += ["-s", sandbox]

    if schema_file and "--output-schema" not in cmd:
        cmd += ["--output-schema", schema_file]

    if result_file and "-o" not in cmd:
        cmd += ["-o", result_file]

    start_time = datetime.now(timezone.utc)
    log_event("adapter_execution_started", task_num=task_num,
             adapter=adapter_name, command=cmd[0])

    with open(log_path, "w", encoding="utf-8") as log_handle:
        child_kwargs = {
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "cwd": workdir,
        }

        if prompt_via_stdin:
            child_kwargs["stdin"] = open(prompt_file, "rb")
        else:
            child_kwargs["stdin"] = subprocess.DEVNULL

        if os.name == "nt":
            child_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            child_kwargs["start_new_session"] = True

        try:
            _WORKER_CHILD = subprocess.Popen(cmd, **child_kwargs)
            log_event("adapter_process_spawned", task_num=task_num,
                     pid=_WORKER_CHILD.pid, adapter=adapter_name)
        except OSError as exc:
            log_handle.write(f"ERROR: 无法启动 adapter {adapter_name}: {exc}\n")
            exit_path.write_text("127\n", encoding="utf-8")
            error_path.write_text(
                json.dumps({
                    "error": "failed_to_start",
                    "adapter": adapter_name,
                    "exception": str(exc),
                    "command": cmd,
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            log_span_end(span_ctx, success=False, reason="failed_to_start", error=str(exc))
            if prompt_via_stdin and "stdin" in child_kwargs:
                child_kwargs["stdin"].close()
            raise SystemExit(127)

        exit_code = _WORKER_CHILD.wait()

        if prompt_via_stdin and "stdin" in child_kwargs:
            child_kwargs["stdin"].close()

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    log_metric("adapter_execution_duration", duration, unit="seconds",
               task_num=task_num, adapter=adapter_name, exit_code=exit_code)

    # 记录非零退出码的错误详情
    if exit_code != 0:
        try:
            log_lines = log_path.read_text(encoding="utf-8").splitlines()
            tail_lines = log_lines[-50:] if len(log_lines) > 50 else log_lines
        except (OSError, UnicodeDecodeError):
            tail_lines = ["(unable to read log)"]

        error_path.write_text(
            json.dumps({
                "error": "non_zero_exit",
                "adapter": adapter_name,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "command": cmd,
                "log_tail": tail_lines,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        log_span_end(span_ctx, success=False, exit_code=exit_code, duration=duration)
    else:
        log_span_end(span_ctx, success=True, exit_code=exit_code, duration=duration)

    exit_path.write_text(f"{exit_code}\n", encoding="utf-8")
    sys.exit(exit_code)
