#!/usr/bin/env python3
"""run_task.py - 执行器抽象层。"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
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
from structured_logging import log_event, log_metric, log_span_start, log_span_end
from tasks_store import CliError, find_task, read_tasks_document
from config import load_config
from task_history import track_execution
from execution_backend import ExecutionBackend
from execution_result import RESULT_SCHEMA
import session_backend


LOGS_DIR = Path(".dual-ai-collab/logs")
HISTORY_DIR = LOGS_DIR / "history"
BACKENDS = ("direct", "plugin", "adapter", "app-server")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
EFFORT_BY_LEVEL = {"quick": "low", "normal": "medium", "heavy": "high"}
SANDBOXES = ("read-only", "workspace-write", "danger-full-access", "provider-default")
_WORKER_CHILD: subprocess.Popen | None = None


def _make_run_id(task_num: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"task-{task_num}-{ts}"


def resolve_exec_options(task_num: str, model: str | None, effort: str | None) -> dict:
    """命令行参数优先，其次任务板的 **模型** / **推理强度**，再由 **执行级别** 推导推理强度。"""
    task = None
    if not (model and effort):
        try:
            task = find_task(read_tasks_document(), task_num)
        except CliError:
            task = None
    if task:
        extras = task.get("extra_fields", {})
        model = model or str(task.get("model") or extras.get("模型", "")).strip() or None
        effort = (
            effort
            or str(extras.get("推理强度", "")).strip()
            or EFFORT_BY_LEVEL.get(task.get("execution_level", ""))
        )
    if effort and effort not in EFFORTS:
        raise CliError(f"不支持的推理强度: {effort}，可选: {', '.join(EFFORTS)}")
    return {"model": model or None, "effort": effort or None}


def build_codex_command(
    workdir: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    schema_file: str | None = None,
    result_file: str | None = None,
    codex_bin: str | None = None,
) -> list[str]:
    """prompt 一律走 stdin（`-`），避免命令行长度限制。

    新版 codex 已移除 --full-auto；-s workspace-write 与其等价且新旧版本通用。
    """
    config = load_config()
    if codex_bin is None:
        codex_bin = config.get("codex_bin", "codex")
    if sandbox is None:
        sandbox = config.get("default_sandbox", "workspace-write")

    if sandbox == "provider-default":
        raise CliError("direct 后端不支持 provider-default，请使用 Codex 沙箱模式")
    cmd = [codex_bin, "exec", "-C", workdir, "-s", sandbox]
    if model:
        cmd += ["-m", model]
    if effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    if schema_file:
        cmd += ["--output-schema", schema_file]
    if result_file:
        cmd += ["-o", result_file]
    cmd.append("-")
    return cmd


def _archive_previous_run(task_num: str) -> None:
    """重试前把上一轮日志和结果移到 history/，当前路径留给新一轮（卡死检测依赖固定路径）。"""
    previous = read_run_record(task_num)
    if not previous:
        return
    if previous.get("status") == "running" and update_run_status(previous).get("status") == "running":
        raise CliError(f"任务 #{task_num} 仍在运行（run_id={previous.get('run_id')}），请先 run stop")
    run_id = previous.get("run_id") or _make_run_id(task_num)
    for key, suffix in (("log_file", ".log"), ("result_file", ".result.json")):
        path = Path(previous.get(key) or "")
        if previous.get(key) and path.exists():
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            path.replace(HISTORY_DIR / f"{run_id}{suffix}")


def read_result(record: dict) -> dict | None:
    path = Path(record.get("result_file") or "")
    if not record.get("result_file") or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_error_details(record: dict) -> dict | None:
    """Read error details file if it exists."""
    log_file = record.get("log_file")
    if not log_file:
        return None
    error_path = Path(log_file).with_suffix(".error.json")
    if not error_path.exists():
        return None
    try:
        return json.loads(error_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _start_direct(task_num: str, prompt: str, workdir: str, options: dict) -> dict:
    span_ctx = log_span_start("task_start", task_num=task_num, backend="direct")

    if (options.get("sandbox") or load_config().get("default_sandbox")) == "provider-default":
        raise CliError("direct 后端不支持 provider-default")
    log_file = LOGS_DIR / f"task-{task_num}.log"
    exit_file = LOGS_DIR / f"task-{task_num}.exit"
    pid_file = LOGS_DIR / f"task-{task_num}.pid"
    prompt_file = LOGS_DIR / f"task-{task_num}.prompt.md"
    result_file = LOGS_DIR / f"task-{task_num}.result.json"
    schema_file = LOGS_DIR / "task-result.schema.json"

    log_file.parent.mkdir(parents=True, exist_ok=True)
    _archive_previous_run(task_num)
    exit_file.unlink(missing_ok=True)
    result_file.unlink(missing_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    log_metric("prompt_size", len(prompt), unit="bytes", task_num=task_num)

    worker_cmd = [
        default_python(),
        str(Path(__file__).resolve()),
        "_worker",
        task_num,
        "--prompt-file",
        str(prompt_file),
        "--workdir",
        workdir,
        "--log-file",
        str(log_file),
        "--exit-file",
        str(exit_file),
    ]
    if options.get("model"):
        worker_cmd += ["--model", options["model"]]
    if options.get("effort"):
        worker_cmd += ["--effort", options["effort"]]

    config = load_config()
    sandbox = options.get("sandbox") or config.get("default_sandbox", "workspace-write")
    worker_cmd += ["--sandbox", sandbox]

    if options.get("structured", True):
        schema_file.write_text(json.dumps(RESULT_SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        worker_cmd += ["--schema-file", str(schema_file), "--result-file", str(result_file)]

    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "cwd": workdir,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(worker_cmd, **popen_kwargs)
        log_event("worker_spawned", task_num=task_num, pid=proc.pid)
    except OSError as exc:
        log_span_end(span_ctx, success=False, error=str(exc))
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
        "prompt_file": str(prompt_file),
        "result_file": str(result_file) if options.get("structured", True) else None,
        "model": options.get("model"),
        "effort": options.get("effort"),
        "sandbox": sandbox,
        "workdir": workdir,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "running",
    }
    write_run_record(record)
    log_span_end(span_ctx, success=True, run_id=record["run_id"])
    return record


def _start_plugin(task_num: str, prompt: str, workdir: str, options: dict) -> dict:
    raise CliError("plugin backend 尚未实现；当前请使用 --backend direct")


def _start_adapter(task_num: str, prompt: str, workdir: str, options: dict) -> dict:
    """使用 adapter backend 启动任务，支持模型路由。"""
    from model_router import resolve_adapter_for_task, resolve_available_adapter, build_adapter_command

    span_ctx = log_span_start("task_start", task_num=task_num, backend="adapter")

    sandbox = options.get("sandbox") or load_config().get("default_sandbox", "workspace-write")
    routing = resolve_available_adapter(resolve_adapter_for_task(task_num), sandbox=sandbox)
    adapter_name = routing["adapter"]
    adapter_cmd = routing["command"]
    sandbox = options.get("sandbox") or load_config().get("default_sandbox", "workspace-write")
    # Fail before spawning a worker when requested permissions cannot be preserved.
    build_adapter_command(routing, workdir, model=options.get("model"), effort=options.get("effort"), sandbox=sandbox)

    log_file = LOGS_DIR / f"task-{task_num}.log"
    exit_file = LOGS_DIR / f"task-{task_num}.exit"
    pid_file = LOGS_DIR / f"task-{task_num}.pid"
    prompt_file = LOGS_DIR / f"task-{task_num}.prompt.md"
    result_file = LOGS_DIR / f"task-{task_num}.result.json"
    schema_file = LOGS_DIR / "task-result.schema.json"

    log_file.parent.mkdir(parents=True, exist_ok=True)
    _archive_previous_run(task_num)
    exit_file.unlink(missing_ok=True)
    result_file.unlink(missing_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    log_metric("prompt_size", len(prompt), unit="bytes", task_num=task_num)
    log_event("adapter_selected", task_num=task_num, adapter=adapter_name,
             reason=routing["reason"])

    worker_cmd = [
        default_python(),
        str(Path(__file__).resolve()),
        "_worker_adapter",
        task_num,
        "--prompt-file",
        str(prompt_file),
        "--workdir",
        workdir,
        "--log-file",
        str(log_file),
        "--exit-file",
        str(exit_file),
        "--adapter-name",
        adapter_name,
        "--adapter-cmd",
        json.dumps(adapter_cmd),
        "--adapter-protocol", routing["protocol"],
    ]

    if options.get("model"):
        worker_cmd += ["--model", options["model"]]
    if options.get("effort"):
        worker_cmd += ["--effort", options["effort"]]

    config = load_config()
    sandbox = options.get("sandbox") or config.get("default_sandbox", "workspace-write")
    worker_cmd += ["--sandbox", sandbox]

    if options.get("structured", True):
        schema_file.write_text(json.dumps(RESULT_SCHEMA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        worker_cmd += ["--schema-file", str(schema_file), "--result-file", str(result_file)]

    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "cwd": workdir,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(worker_cmd, **popen_kwargs)
        log_event("worker_spawned", task_num=task_num, pid=proc.pid, adapter=adapter_name)
    except OSError as exc:
        log_span_end(span_ctx, success=False, error=str(exc))
        raise CliError(f"无法启动后台 worker: {exc}") from exc

    pid_file.write_text(f"{proc.pid}\n", encoding="utf-8")

    record = {
        "run_id": _make_run_id(task_num),
        "task_num": task_num,
        "backend": "adapter",
        "adapter": adapter_name,
        "adapter_protocol": routing["protocol"],
        "pid": proc.pid,
        "log_file": str(log_file),
        "exit_file": str(exit_file),
        "pid_file": str(pid_file),
        "prompt_file": str(prompt_file),
        "result_file": str(result_file) if options.get("structured", True) else None,
        "model": options.get("model"),
        "effort": options.get("effort"),
        "sandbox": sandbox,
        "workdir": workdir,
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "running",
    }
    write_run_record(record)
    log_span_end(span_ctx, success=True, run_id=record["run_id"], adapter=adapter_name)
    return record


def _status_direct(record: dict) -> dict:
    record = update_run_status(record)
    if record.get("status") not in {"running", "starting", "stopping"}:
        record["result"] = read_result(record)
        if record.get("status") == "failed":
            record["error_details"] = read_error_details(record)
    return record


def _status_plugin(record: dict) -> dict:
    raise CliError("plugin backend 尚未实现")


def _stop_direct(record: dict) -> dict:
    return stop_run_record(record)


def _stop_plugin(record: dict) -> dict:
    raise CliError("plugin backend 尚未实现")


def _status_adapter(record: dict) -> dict:
    """adapter backend 使用与 direct 相同的状态检测逻辑。"""
    return _status_direct(record)


def _stop_adapter(record: dict) -> dict:
    """adapter backend 使用与 direct 相同的停止逻辑。"""
    return _stop_direct(record)


_BACKEND_DISPATCH = {
    "direct": {"start": _start_direct, "status": _status_direct, "stop": _stop_direct},
    "plugin": {"start": _start_plugin, "status": _status_plugin, "stop": _stop_plugin},
    "adapter": {"start": _start_adapter, "status": _status_adapter, "stop": _stop_adapter},
    "app-server": {"start": session_backend.start, "status": session_backend.status,
                   "stop": session_backend.stop, "continue": session_backend.continue_task,
                   "steer": session_backend.steer, "events": session_backend.events,
                   "complete": session_backend.complete},
}


def get_backend(name):
    if name not in _BACKEND_DISPATCH:
        raise CliError(f"未知执行后端: {name}")
    return ExecutionBackend(name, _BACKEND_DISPATCH[name] if name != "plugin" else {})


def cmd_worker(
    task_num: str,
    prompt_file: str,
    workdir: str,
    log_file: str,
    exit_file: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    schema_file: str | None = None,
    result_file: str | None = None,
) -> None:
    global _WORKER_CHILD
    os.chdir(workdir)

    with track_execution(task_num, adapter="codex", model=model, prompt_file=prompt_file):
        config = load_config()
        if sandbox is None:
            sandbox = config.get("default_sandbox", "workspace-write")

        span_ctx = log_span_start("worker_execution", task_num=task_num, model=model, effort=effort)

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
            # Record signal termination
            error_path.write_text(
                json.dumps({"error": "terminated_by_signal", "signal": _signum}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            log_span_end(span_ctx, success=False, reason="terminated_by_signal", signal=_signum)
            raise SystemExit(143)

        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, _handle_signal)

        codex_cmd = build_codex_command(
            workdir, model=model, effort=effort, sandbox=sandbox, schema_file=schema_file, result_file=result_file
        )

        start_time = datetime.now(timezone.utc)
        log_event("codex_execution_started", task_num=task_num, command=codex_cmd[0])

        with open(log_path, "w", encoding="utf-8") as log_handle, open(prompt_file, "rb") as prompt_handle:
            child_kwargs = {
                "stdout": log_handle,
                "stderr": subprocess.STDOUT,
                "stdin": prompt_handle,
            }
            if os.name == "nt":
                child_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                child_kwargs["start_new_session"] = True

            try:
                _WORKER_CHILD = subprocess.Popen(codex_cmd, **child_kwargs)
                log_event("codex_process_spawned", task_num=task_num, pid=_WORKER_CHILD.pid)
            except OSError as exc:
                log_handle.write(f"ERROR: 无法启动 codex: {exc}\n")
                exit_path.write_text("127\n", encoding="utf-8")
                error_path.write_text(
                    json.dumps({
                        "error": "failed_to_start",
                        "exception": str(exc),
                        "command": codex_cmd,
                    }, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8"
                )
                log_span_end(span_ctx, success=False, reason="failed_to_start", error=str(exc))
                raise SystemExit(127)

            exit_code = _WORKER_CHILD.wait()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        log_metric("codex_execution_duration", duration, unit="seconds",
                   task_num=task_num, exit_code=exit_code)

        # Record error details for non-zero exit codes
        if exit_code != 0:
            # Extract last 50 lines of log for error context
            try:
                log_lines = log_path.read_text(encoding="utf-8").splitlines()
                tail_lines = log_lines[-50:] if len(log_lines) > 50 else log_lines
            except (OSError, UnicodeDecodeError):
                tail_lines = ["(unable to read log)"]

            error_path.write_text(
                json.dumps({
                    "error": "non_zero_exit",
                    "exit_code": exit_code,
                    "duration_seconds": duration,
                    "command": codex_cmd,
                    "log_tail": tail_lines,
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            log_span_end(span_ctx, success=False, exit_code=exit_code)
        else:
            log_span_end(span_ctx, success=True, exit_code=exit_code)

        exit_path.write_text(f"{exit_code}\n", encoding="utf-8")
        sys.exit(exit_code)


def cmd_worker_adapter(
    task_num: str,
    prompt_file: str,
    workdir: str,
    log_file: str,
    exit_file: str,
    adapter_name: str,
    adapter_cmd: str,
    *,
    adapter_protocol: str = "codex",
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    schema_file: str | None = None,
    result_file: str | None = None,
) -> None:
    """Adapter backend worker - 运行适配器命令。"""
    global _WORKER_CHILD
    os.chdir(workdir)

    with track_execution(task_num, adapter=adapter_name, model=model, prompt_file=prompt_file):
        config = load_config()
        if sandbox is None:
            sandbox = config.get("default_sandbox", "workspace-write")

        # 解析 adapter_cmd JSON
        try:
            adapter_cmd_list = json.loads(adapter_cmd)
        except json.JSONDecodeError as exc:
            raise CliError(f"无法解析 adapter_cmd JSON: {exc}") from exc

        span_ctx = log_span_start("adapter_execution", task_num=task_num, adapter=adapter_name, model=model, effort=effort)

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
                json.dumps({"error": "terminated_by_signal", "signal": _signum}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            log_span_end(span_ctx, success=False, reason="terminated_by_signal", signal=_signum)
            raise SystemExit(143)

        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, _handle_signal)

        # 构建适配器命令
        from model_router import build_adapter_command

        adapter_config = {"adapter": adapter_name, "command": adapter_cmd_list, "protocol": adapter_protocol}
        full_cmd = build_adapter_command(
            adapter_config, workdir, model=model, effort=effort, sandbox=sandbox,
            schema_file=schema_file, result_file=result_file
        )

        start_time = datetime.now(timezone.utc)
        log_event("adapter_execution_started", task_num=task_num, adapter=adapter_name, command=full_cmd[0])

        stdout_path = log_path.with_suffix(".stdout.json") if adapter_protocol == "claude" else log_path
        with open(log_path, "w", encoding="utf-8") as log_handle, (open(stdout_path, "w", encoding="utf-8") if adapter_protocol == "claude" else nullcontext(log_handle)) as stdout_handle, open(prompt_file, "rb") as prompt_handle:
            child_kwargs = {
                "stdout": stdout_handle if adapter_protocol == "claude" else log_handle,
                "stderr": log_handle if adapter_protocol == "claude" else subprocess.STDOUT,
                "stdin": prompt_handle,
            }
            if os.name == "nt":
                child_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            else:
                child_kwargs["start_new_session"] = True

            try:
                _WORKER_CHILD = subprocess.Popen(full_cmd, **child_kwargs)
                log_event("adapter_process_spawned", task_num=task_num, pid=_WORKER_CHILD.pid, adapter=adapter_name)
            except OSError as exc:
                log_handle.write(f"ERROR: 无法启动 adapter {adapter_name}: {exc}\n")
                exit_path.write_text("127\n", encoding="utf-8")
                error_path.write_text(
                    json.dumps({
                        "error": "failed_to_start",
                        "exception": str(exc),
                        "adapter": adapter_name,
                        "command": full_cmd,
                    }, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8"
                )
                log_span_end(span_ctx, success=False, reason="failed_to_start", error=str(exc))
                raise SystemExit(127)

            exit_code = _WORKER_CHILD.wait()

        if adapter_protocol == "claude":
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(stdout_path.read_text(encoding="utf-8"))
            if exit_code == 0:
                try:
                    from model_router import normalize_claude_output
                    normalize_claude_output(stdout_path, result_file, schema_file)
                except CliError as exc:
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(f"\nERROR: {exc}\n")
                    exit_code = 1

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        log_metric("adapter_execution_duration", duration, unit="seconds",
                   task_num=task_num, adapter=adapter_name, exit_code=exit_code)

        if exit_code != 0:
            try:
                log_lines = log_path.read_text(encoding="utf-8").splitlines()
                tail_lines = log_lines[-50:] if len(log_lines) > 50 else log_lines
            except (OSError, UnicodeDecodeError):
                tail_lines = ["(unable to read log)"]

            error_path.write_text(
                json.dumps({
                    "error": "non_zero_exit",
                    "exit_code": exit_code,
                    "duration_seconds": duration,
                    "adapter": adapter_name,
                    "command": full_cmd,
                    "log_tail": tail_lines,
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8"
            )
            log_span_end(span_ctx, success=False, exit_code=exit_code)
        else:
            log_span_end(span_ctx, success=True, exit_code=exit_code)

        exit_path.write_text(f"{exit_code}\n", encoding="utf-8")
        sys.exit(exit_code)


def _load_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise CliError("prompt 与 --prompt-file 只能二选一")
    if prompt_file:
        try:
            prompt = Path(prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(f"无法读取 prompt 文件: {prompt_file} ({exc})") from exc
    if not prompt or not prompt.strip():
        raise CliError("缺少任务提示词：传入 prompt 或 --prompt-file")
    return prompt


def cmd_start(
    task_num: str,
    prompt: str,
    backend: str,
    workdir: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    structured: bool = True,
    isolate: bool = False,
    context_task_file: str | None = None,
    timeout: float | None = None,
) -> int:
    from run_support import preflight
    preflight(task_num, workdir, context_task_file or "planning/codex-tasks.md")
    config = load_config()
    if backend is None:
        backend = config.get("default_backend", "direct")
    if backend not in BACKENDS:
        raise CliError(f"不支持的 backend: {backend}，可选: {', '.join(BACKENDS)}")

    options = resolve_exec_options(task_num, model, effort)
    options["structured"] = structured
    options["sandbox"] = sandbox or config.get("default_sandbox", "workspace-write")
    task_num = session_backend.task_id(task_num)
    if backend != "app-server" and (isolate or timeout is not None or context_task_file):
        raise CliError("--isolate / --timeout / --context-task-file 目前仅用于 app-server 后端")
    options.update(isolate=isolate, timeout=timeout, context_task_file=context_task_file)
    if backend == "app-server":
        record = get_backend(backend).call("start", task_num, prompt, workdir, options)
    else:
        with session_backend.lock(task_num):
            previous = session_backend._ensure_idle(task_num)
            if previous.get("backend") == "app-server":
                raise CliError("此任务已有 app-server 会话，请 continue 或使用新的任务编号")
            record = get_backend(backend).call("start", task_num, prompt, workdir, options)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def cmd_status(task_num: str) -> int:
    task_num = session_backend.task_id(task_num)
    record = read_run_record(task_num)
    if not record:
        print(simple_run_status(task_num))
        return 0
    backend = record.get("backend", "direct")
    result = get_backend(backend).call("status", record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_stop(task_num: str) -> int:
    task_num = session_backend.task_id(task_num)
    record = read_run_record(task_num)
    if not record:
        result = stop_task(task_num)
        print(result["status"] if result else "not_found")
        return 0

    if record.get("status") != "running":
        print(f"SKIP: 任务 #{task_num} 当前状态为 {record.get('status')}，无需终止")
        return 0

    backend = record.get("backend", "direct")
    result = get_backend(backend).call("stop", record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _add_start_arguments(p_start) -> None:
    p_start.add_argument("task_num")
    p_start.add_argument("prompt", nargs="?", default=None)
    p_start.add_argument("--prompt-file", default=None, help="从文件读取提示词（长提示词推荐）")
    p_start.add_argument("--backend", default=None, choices=BACKENDS)
    p_start.add_argument("--workdir", default=None)
    p_start.add_argument("--model", default=None, help="覆盖任务板 **模型**")
    p_start.add_argument("--effort", default=None, choices=EFFORTS, help="覆盖任务板 **推理强度** / 执行级别推导值")
    p_start.add_argument("--sandbox", default=None, choices=SANDBOXES, help="沙箱模式（默认从配置读取）")
    p_start.add_argument("--context-task-file", help="app-server: 每轮自动刷新此任务板的上下文快照")
    p_start.add_argument("--isolate", action="store_true", help="app-server: 从干净的 Git HEAD 创建独立 worktree")
    p_start.add_argument("--timeout", type=float, help="app-server: 单轮执行超时秒数")
    p_start.add_argument("--no-structured", action="store_true", help="不使用 --output-schema 结构化结果")


def register_subparsers(subparsers, *, nested: bool = False):
    if nested:
        run_parser = subparsers.add_parser("run", help="任务执行器")
        run_sub = run_parser.add_subparsers(dest="run_command")

        _add_start_arguments(run_sub.add_parser("start", help="启动任务执行"))

        p_status = run_sub.add_parser("status", help="查询运行状态")
        p_status.add_argument("task_num")

        p_stop = run_sub.add_parser("stop", help="终止运行中的任务")
        p_stop.add_argument("task_num")
        register_session_commands(run_sub)
        return run_parser

    _add_start_arguments(subparsers.add_parser("start", help="启动任务执行"))

    p_status = subparsers.add_parser("status", help="查询运行状态")
    p_status.add_argument("task_num")

    p_stop = subparsers.add_parser("stop", help="终止运行中的任务")
    p_stop.add_argument("task_num")
    register_session_commands(subparsers)

    p_worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    p_worker.add_argument("task_num")
    p_worker.add_argument("--prompt-file", required=True)
    p_worker.add_argument("--workdir", required=True)
    p_worker.add_argument("--log-file", required=True)
    p_worker.add_argument("--exit-file", required=True)
    p_worker.add_argument("--model", default=None)
    p_worker.add_argument("--effort", default=None)
    p_worker.add_argument("--sandbox", default=None, choices=SANDBOXES)
    p_worker.add_argument("--schema-file", default=None)
    p_worker.add_argument("--result-file", default=None)

    p_worker_adapter = subparsers.add_parser("_worker_adapter", help=argparse.SUPPRESS)
    p_worker_adapter.add_argument("task_num")
    p_worker_adapter.add_argument("--prompt-file", required=True)
    p_worker_adapter.add_argument("--workdir", required=True)
    p_worker_adapter.add_argument("--log-file", required=True)
    p_worker_adapter.add_argument("--exit-file", required=True)
    p_worker_adapter.add_argument("--adapter-name", required=True)
    p_worker_adapter.add_argument("--adapter-cmd", required=True)
    p_worker_adapter.add_argument("--adapter-protocol", default="codex", choices=("codex", "claude"))
    p_worker_adapter.add_argument("--model", default=None)
    p_worker_adapter.add_argument("--effort", default=None)
    p_worker_adapter.add_argument("--sandbox", default=None, choices=SANDBOXES)
    p_worker_adapter.add_argument("--schema-file", default=None)
    p_worker_adapter.add_argument("--result-file", default=None)
    return None


def register_session_commands(subparsers):
    parser = subparsers.add_parser("verify-manual", help="逐项确认并记录手动验收，不改变执行结果")
    parser.add_argument("task_num")
    parser.add_argument("--task-file", default="planning/codex-tasks.md")
    parser.add_argument("--note")
    parser.add_argument("--confirm", type=int, action="append", help="确认已实际通过的标准编号，可重复")
    parser.add_argument("--list", action="store_true", help="只列出验收标准编号")
    parser = subparsers.add_parser("watch", help="持续显示纯文本状态，终态自动退出")
    parser.add_argument("task_num")
    parser.add_argument("--interval", type=float, default=5)

    caps = subparsers.add_parser("capabilities", help="查看执行后端能力")
    caps.add_argument("--backend", choices=BACKENDS)
    for name in ("continue", "steer"):
        parser = subparsers.add_parser(name, help="继续已有会话" if name == "continue" else "向运行中的会话追加指导")
        parser.add_argument("task_num")
        parser.add_argument("prompt", nargs="?")
        parser.add_argument("--prompt-file")
    parser = subparsers.add_parser("events", help="读取当前轮事件（游标按 run_id 独立）")
    parser.add_argument("task_num")
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser = subparsers.add_parser("complete", help="在执行工作目录验收，通过后进入 AWAITING_REVIEW")
    parser.add_argument("task_num")
    parser.add_argument("--task-file", default="planning/codex-tasks.md")
    parser.add_argument("--repair", action="store_true", help="验收失败后恢复原会话修复一次，不自动循环")


def dispatch(args) -> int:
    operation = getattr(args, "run_command", None) or getattr(args, "command", None)
    if operation == "verify-manual":
        from run_support import verify_manual
        return verify_manual(args)
    if operation == "watch":
        from run_support import watch
        return watch(args.task_num, args.interval)
    if operation == "capabilities":
        names = [args.backend] if args.backend else BACKENDS
        print(json.dumps({name: get_backend(name).capabilities() for name in names}, ensure_ascii=False, indent=2))
        return 0
    if operation in {"continue", "steer", "events", "complete"}:
        task_num = session_backend.task_id(args.task_num)
        record = read_run_record(task_num)
        if not record:
            raise CliError("未找到运行记录")
        backend = get_backend(record.get("backend", "direct"))
        if operation in {"continue", "steer"}:
            result = backend.call(operation, task_num, _load_prompt(args.prompt, args.prompt_file))
        elif operation == "events":
            result = backend.call(operation, task_num, args.after, args.limit)
        else:
            result = backend.call(operation, task_num, args.repair, args.task_file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if operation == "complete" and not result["passed"] else 0

    if getattr(args, "command", None) == "_worker":
        cmd_worker(
            args.task_num,
            args.prompt_file,
            args.workdir,
            args.log_file,
            args.exit_file,
            model=args.model,
            effort=args.effort,
            sandbox=args.sandbox,
            schema_file=args.schema_file,
            result_file=args.result_file,
        )
        return 0

    if getattr(args, "command", None) == "_worker_adapter":
        cmd_worker_adapter(
            args.task_num,
            args.prompt_file,
            args.workdir,
            args.log_file,
            args.exit_file,
            args.adapter_name,
            args.adapter_cmd,
            adapter_protocol=args.adapter_protocol,
            model=args.model,
            effort=args.effort,
            sandbox=args.sandbox,
            schema_file=args.schema_file,
            result_file=args.result_file,
        )
        return 0

    if getattr(args, "run_command", None) == "start" or getattr(args, "command", None) == "start":
        workdir = args.workdir or os.getcwd()
        prompt = _load_prompt(args.prompt, args.prompt_file)
        return cmd_start(
            args.task_num,
            prompt,
            args.backend,
            workdir,
            model=args.model,
            effort=args.effort,
            sandbox=args.sandbox,
            structured=not args.no_structured,
            isolate=args.isolate, timeout=args.timeout, context_task_file=args.context_task_file,
        )
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
