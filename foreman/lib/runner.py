"""Invoke the user-selected dispatcher with Task only and record each attempt."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .board import TaskBoard
from .config import ExecutionConfig
from .probe import verify_receipt
from .safety import (
    AUTONOMY,
    check_capabilities,
    minimal_environment,
    runtime_policy,
    write_policy,
)
from .store import _file_scope
from .team import check_team, list_byok_models
from .workflow import Workflow, now

READ_TOOLS = ["Read", "LS", "Grep", "Glob"]
WRITE_TOOLS = ["Create", "Edit", "ApplyPatch", "Execute"]


def dispatch_events(output: str, exit_code: int) -> tuple[str, dict]:
    """Interpret transport events, not the dispatcher's natural-language claims."""
    events = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append(value)
    terminals = [e for e in events if e.get("type") in {"completion", "result"}]
    tool_errors = sum(bool(e.get("isError") or e.get("is_error") or e.get("error"))
                      for e in events if e.get("type") == "tool_result")
    permission = any((e.get("subtype") or e.get("status") or e.get("reason")) == "permission_rejected"
                     for e in events)
    errors = [e for e in events if e.get("type") == "tool_result"
              and (e.get("isError") or e.get("is_error") or e.get("error"))]
    categories = []
    for event in errors:
        text = json.dumps(event).lower()
        categories.append("daemon_unavailable" if "could not reach the daemon" in text else "tool_error")
    outcome = "failed"
    if permission:
        outcome = "permission_rejected"
    elif exit_code == 0 and terminals and not tool_errors and not any(
        e.get("is_error") or e.get("isError") or e.get("error") for e in terminals
    ):
        outcome = "returned"
    session = next((e["session_id"] for e in events if e.get("type") == "system" and e.get("session_id")), None)
    return outcome, {"terminal_event": bool(terminals), "tool_errors": tool_errors,
                     "error_categories": sorted(set(categories)), "dispatcher_session": session,
                     "dispatcher_tools": [e.get("toolName") for e in events if e.get("type") == "tool_call"]}


def run_task(root: Path, task_id: str, dispatcher: str, timeout: int = 1800,
             settings_path: Path | None = None, executable: str = "droid") -> dict:
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    root = root.resolve()
    # The task comes first: one without a role needs neither a dispatcher model nor droid.
    task = TaskBoard.load(root).get_task(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")
    if not task.get("role"):
        raise ValueError("任务没有 role，由当前会话直接执行：用 execution begin 登记后自己实现；"
                         "要派发就先给任务写上 role")
    if dispatcher not in {m["id"] for m in list_byok_models(settings_path)}:
        raise ValueError(f"调度模型 {dispatcher} 不在已配置的模型里：必须是用户选定的完整 BYOK ID，"
                         "即 foreman models 的第一列")
    check_capabilities(executable)
    checks = [c for c in check_team(root, settings_path=settings_path) if c["role"] == task.get("role")]
    if not checks or not all(c["ok"] for c in checks):
        problems = "；".join(p for c in checks for p in c["problems"]) or f"角色 {task['role']} 未配置"
        raise ValueError(f"任务角色预检失败（{problems}）；不能自动换模型，处理后用 foreman team check 确认")
    verify_receipt(root, dispatcher, executable)
    workflow = Workflow(root)
    plan = workflow.begin(task_id)
    execution_id = plan["execution_id"]
    outcome = "failed"
    code = None
    process = None
    transport = {}
    try:
        with tempfile.TemporaryDirectory(prefix="tm-dispatch-", dir=root) as tmp:
            # Hooks run inside the sandbox: the guard's own files stay read-only, and it
            # gets one writable place to record which session is the dispatcher.
            guard_dir = Path(tmp) / "guard"
            state = Path(tmp) / "state" / "dispatcher"
            guard_dir.mkdir()
            state.parent.mkdir()
            policy_path = guard_dir / "runtime.json"
            guard = guard_dir / "guard.py"
            source = Path(__file__).resolve().parents[1] / "tools" / "dispatch_guard.py"
            guard.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            guard_policy = guard_dir / "guard-policy.json"
            write_policy(guard_policy, {
                "root": str(root), "task_args": plan["task_args"], "state": str(state),
                "write_scopes": [str(root / _file_scope(path)) for path in plan["files"]],
            })
            policy = runtime_policy(root)
            policy["sandbox"]["filesystem"]["denyWrite"].append(str(guard_dir))
            policy["hooks"] = {"PreToolUse": [{
                "matcher": "*", "hooks": [{"type": "command", "command":
                    f"{shlex.quote(sys.executable)} {shlex.quote(str(guard))} {shlex.quote(str(guard_policy))}",
                    "timeout": 10}],
            }]}
            write_policy(policy_path, policy)
            prompt = (
                "只调用一次 Task，参数严格使用下面的 JSON。等待子 Agent 完成后原样转述它的报告。"
                "不要实现、检查、重试、换模型或额外派发：除这一次 Task 外，你的其他工具调用都会被拒绝。"
                "\n" + json.dumps(plan["task_args"], ensure_ascii=False)
            )
            # A worker inherits the dispatcher's tool list, so the worker's tools have to be
            # listed here; the guard holds the dispatcher session itself to the one Task call.
            role = ExecutionConfig(root).get_role(task.get("role")) or {}
            worker_tools = READ_TOOLS if role.get("read_only") else READ_TOOLS + WRITE_TOOLS
            process = subprocess.Popen(
                [executable, "exec", "--model", dispatcher, "--only-tools", ",".join(["Task", *worker_tools]),
                 "--settings", str(policy_path), "--output-format", "stream-json", "--auto", AUTONOMY, prompt],
                cwd=root, env=minimal_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
            try:
                output, _ = process.communicate(timeout=timeout)
                code = process.returncode
                outcome, transport = dispatch_events(output, code)
                claimed = state.read_text(encoding="utf-8").strip() if state.exists() else ""
                # The state file is writable from the sandbox; trust it only when it names
                # the session droid itself reported as the dispatcher.
                if outcome == "returned" and claimed != transport["dispatcher_session"]:
                    outcome = "failed"
                    transport["error_categories"].append("guard_state_mismatch")
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                outcome = "interrupted"
            except KeyboardInterrupt:
                outcome = "interrupted"
                raise
    except KeyboardInterrupt:
        outcome = "interrupted"
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        ended_at = now()
        try:
            audit = workflow.audit(execution_id)
        except (OSError, ValueError):
            audit = {"status": "unverified", "records": []}
            transport["audit_error"] = True
            outcome = "failed"
        if outcome == "returned" and not audit["records"]:
            # The dispatcher may return normally after a Task launch error.
            outcome = "failed"
        # The dispatcher also returns normally when the worker itself was stopped; only the
        # worker's own session says how it ended. Unrecorded (None) is left as it is.
        worker = audit["records"][0].get("outcome") if len(audit["records"]) == 1 else None
        transport["worker_outcome"] = worker
        if outcome == "returned" and worker not in (None, "completed"):
            outcome = "permission_rejected" if worker == "permission_rejected" else "failed"
        workflow.finish(execution_id, outcome, ended_at=ended_at, transport=transport)
    return {"execution_id": execution_id, "dispatch_outcome": outcome, "exit_code": code,
            "transport": transport, "audit": audit, "inspection": workflow.inspect(execution_id)}
