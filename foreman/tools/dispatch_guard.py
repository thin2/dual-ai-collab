#!/usr/bin/env python3
"""Per-run tool contract. Native sandbox, not this hook, confines shell processes."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")


def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def claim_dispatcher(state: Path, session: str) -> bool:
    """Record the first Task caller as the dispatcher; a second Task call finds the file taken."""
    try:
        descriptor = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(session)
    return True


def validate(event: dict, policy: dict) -> str | None:
    name = event.get("tool_name", "")
    args = event.get("tool_input", {})
    session = event.get("session_id")
    state = policy.get("state")
    if not isinstance(args, dict) and name != "ApplyPatch":
        return "工具参数必须是对象"
    if name == "Task":
        expected = policy["task_args"]
        if any(args.get(k) != v for k, v in expected.items()) or args.get("complexity"):
            return "只能派发当前任务和用户选定的角色，不允许换模型或另派任务"
        if state and not (isinstance(session, str) and session and claim_dispatcher(Path(state), session)):
            return "本次派发只允许调用一次 Task；不要重试或另派"
        return None
    # Script itself has no filesystem/network API; each nested tool call
    # arrives here as its own event.
    if name in {"TodoWrite", "Script", "WaitForScript"}:
        return None
    if state:
        # A worker inherits the dispatcher's tool list, so the worker's tools are also
        # present in the dispatcher session. Only the session id tells them apart.
        try:
            dispatcher = Path(state).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            dispatcher = ""
        if not dispatcher or not session or session == dispatcher:
            return "调度会话只能调用一次 Task；不要自行实现或检查，直接转述子 Agent 的报告"
    if name == "Execute":
        if "cwd" in args or not all(args.get(k) for k in ("command", "riskLevel", "summary")):
            return "Execute 需要 command、riskLevel、summary；不要使用 cwd 参数"
        if args["riskLevel"] not in {"low", "medium", "high"}:
            return "无效的 riskLevel"
        return None
    root = Path(policy["root"]).resolve()
    writes = name in {"Edit", "Create", "ApplyPatch"}
    if name == "ApplyPatch":
        patch = args if isinstance(args, str) else args.get("input", args.get("patch", ""))
        # Inspect patch headers only; ordinary document text mentioning secrets is fine.
        paths = re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", patch, re.MULTILINE)
        if not paths:
            return "无法识别补丁目标，停止并报告"
    elif name in {"Read", "Edit", "Create", "Grep", "Glob", "LS"}:
        paths = [args.get("file_path") or args.get("path") or args.get("folder")
                 or args.get("directory_path") or str(root)]
    else:
        return "此派发未授权该工具；不要绕过限制，报告所需能力"
    for value in paths:
        path = Path(value)
        path = (root / path).resolve()
        if not within(path, root):
            return "只允许访问当前项目，外部上下文由主 Agent 提供"
        relative = path.relative_to(root)
        if any(part in {".git", ".factory", ".task-management", ".ssh", ".aws"}
               or (part.startswith(".env") and not part.endswith(ENV_TEMPLATE_SUFFIXES))
               or part.endswith((".key", ".pem"))
               or part in {"credentials", "credentials.json", "secrets.json"} for part in relative.parts):
            return "目标路径受保护"
        if writes and not any(within(path, Path(scope).resolve()) for scope in policy["write_scopes"]):
            return "写入超出任务声明的 files，停止并报告"
    return None


def main():
    try:
        policy = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        problem = validate(json.load(sys.stdin), policy)
    except (OSError, ValueError, TypeError, KeyError):
        problem = "无法验证工具参数，拒绝执行"
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
