#!/usr/bin/env python3
"""task_manager.py - 任务编排核心。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from platform_utils import FileLock, find_recent_code_changes, is_process_running
from tasks_store import (
    CliError,
    DEFAULT_TASKS_MD,
    all_dependencies_satisfied,
    atomic_write,
    find_task,
    has_dependencies,
    open_tasks_sorted,
    read_tasks_document,
    report_missing_status,
    require_explicit_status,
    resolve_stall_minutes,
    resolve_task_paths,
    write_tasks_document,
)


class CheckpointStore:
    ALLOWED_FIELDS = {
        "spec_file",
        "task_file",
        "current_task",
        "total_tasks",
        "completed_tasks",
        "fix_round",
    }
    VALID_PHASES = {
        "interview",
        "spec_generated",
        "tasks_created",
        "user_approved",
        "developing",
        "auditing",
        "fixing",
    }
    CHECKPOINT_DIR = Path(".dual-ai-collab/checkpoints")
    STATE_FILE = CHECKPOINT_DIR / "state.json"
    LOCK_FILE = CHECKPOINT_DIR / "state.json.lock"

    @classmethod
    def read(cls) -> dict:
        if not cls.STATE_FILE.exists():
            return {}
        try:
            with open(cls.STATE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            backup = cls.STATE_FILE.with_suffix(cls.STATE_FILE.suffix + ".corrupted")
            shutil.copy2(cls.STATE_FILE, backup)
            print(f"WARNING: 现有 checkpoint 非法，已备份到 {backup.name}，将重新生成。", file=sys.stderr)
        return {}

    @classmethod
    def write(cls, phase: str, extra_args: list[str]) -> str:
        if phase not in cls.VALID_PHASES:
            raise CliError(f"无效的 phase 值: {phase}；允许: {'|'.join(sorted(cls.VALID_PHASES))}")

        cls.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with FileLock(cls.LOCK_FILE):
            data = cls.read()
            for item in extra_args:
                if "=" not in item:
                    raise CliError(f"非法参数 '{item}'，必须使用 key=value 格式。")
                key, value = item.split("=", 1)
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    raise CliError(f"非法字段名 '{key}'。")
                if key not in cls.ALLOWED_FIELDS:
                    print(
                        f"WARNING: 未知字段 '{key}' 被忽略（允许: {', '.join(sorted(cls.ALLOWED_FIELDS))}）",
                        file=sys.stderr,
                    )
                    continue
                data[key] = value

            data["phase"] = phase
            data["updated_at"] = updated_at

            ordered = {"phase": data["phase"], "updated_at": data["updated_at"]}
            for key in ("spec_file", "task_file", "current_task", "total_tasks", "completed_tasks", "fix_round"):
                value = data.get(key)
                if value not in (None, ""):
                    ordered[key] = value

            atomic_write(cls.STATE_FILE, json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
        return updated_at

    @classmethod
    def check(cls) -> tuple[str, str]:
        if not cls.STATE_FILE.exists():
            return "missing", ""
        try:
            with open(cls.STATE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("checkpoint root must be an object")
        except (json.JSONDecodeError, ValueError):
            backup = cls.STATE_FILE.with_suffix(cls.STATE_FILE.suffix + ".corrupted")
            shutil.copy2(cls.STATE_FILE, backup)
            return "corrupted", backup.name
        return "found", json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _task_lock_path(task_file: str | Path) -> Path:
    return resolve_task_paths(task_file).json_path.with_suffix(".json.lock")


def cmd_init() -> int:
    for directory in (
        "planning/specs",
        "planning/audit-reports",
        "planning/progress-reports",
        ".dual-ai-collab/logs",
        ".dual-ai-collab/checkpoints",
        ".dual-ai-collab/designs",
    ):
        Path(directory).mkdir(parents=True, exist_ok=True)
    print("ENV_READY")
    return 0


def cmd_update(task_num: str, new_status: str, task_file: str) -> int:
    with FileLock(_task_lock_path(task_file)):
        document = read_tasks_document(task_file)
        target = find_task(document, task_num)
        if target is None:
            raise CliError(f"未找到任务 #{task_num}")
        require_explicit_status(target, task_file)

        old_status = target["status"]
        if old_status == new_status:
            print(f"SKIP: 任务 #{task_num} 已经是 {new_status}")
            return 0

        target["status"] = new_status
        target["status_explicit"] = True
        if "status" not in target.get("field_order", []):
            target.setdefault("field_order", []).insert(0, "status")
        write_tasks_document(document, task_file)

    print(f"OK: 任务 #{task_num} {old_status} -> {new_status}")
    return 0


def cmd_select(parallel: bool, task_file: str) -> int:
    document = read_tasks_document(task_file)
    tasks = document["tasks"]
    for task in tasks:
        require_explicit_status(task, task_file)

    open_tasks = open_tasks_sorted(document)
    if not open_tasks:
        print("NO_OPEN_TASKS")
        return 0

    if parallel:
        lines = []
        for task in open_tasks:
            if not has_dependencies(task["dependencies"]):
                priority = int(re.match(r"P(\d)", task.get("priority", "P9")).group(1)) if re.match(
                    r"P(\d)", task.get("priority", "P9")
                ) else 9
                lines.append(f"{priority}|{task['id']}|{task['dependencies']}")
        print("\n".join(lines) if lines else "NO_PARALLEL_TASKS")
        return 0

    for task in open_tasks:
        if all_dependencies_satisfied(tasks, task["dependencies"]):
            priority_match = re.match(r"P(\d)", task.get("priority", "P9"))
            priority = int(priority_match.group(1)) if priority_match else 9
            print(f"{priority}|{task['id']}|{task['dependencies']}")
            return 0

    print("NO_EXECUTABLE_TASKS")
    return 0


def cmd_checkpoint_write(phase: str, extra_args: list[str]) -> int:
    updated_at = CheckpointStore.write(phase, extra_args)
    print(f"CHECKPOINT: phase={phase} updated_at={updated_at}")
    return 0


def cmd_checkpoint_check() -> int:
    status, content = CheckpointStore.check()
    if status == "found":
        print("CHECKPOINT_FOUND")
        print(content, end="")
    elif status == "corrupted":
        print("CHECKPOINT_CORRUPTED")
        print(content)
    else:
        print("NO_CHECKPOINT")
    return 0


def cmd_detect(task_num: str, codex_pid: str, task_file: str) -> int:
    try:
        pid = int(codex_pid)
    except ValueError as exc:
        raise CliError(f"非法 PID: {codex_pid}") from exc

    try:
        document = read_tasks_document(task_file)
        task = find_task(document, task_num)
    except CliError:
        task = None
    stall_minutes = resolve_stall_minutes(task)

    log_file = Path(f".dual-ai-collab/logs/task-{task_num}.log")
    state_file = Path(f".dual-ai-collab/logs/task-{task_num}.stall-state")
    pid_file = Path(f".dual-ai-collab/logs/task-{task_num}.pid")
    exit_file = Path(f".dual-ai-collab/logs/task-{task_num}.exit")

    if not is_process_running(pid):
        exit_code = 1
        trust_exit_file = False
        if pid_file.exists():
            try:
                trust_exit_file = pid_file.read_text(encoding="utf-8").strip() == str(pid)
            except OSError:
                trust_exit_file = False
        if exit_file.exists() and trust_exit_file:
            try:
                exit_code = int(exit_file.read_text(encoding="utf-8").strip())
            except ValueError:
                exit_code = 1
        state_file.unlink(missing_ok=True)
        print("SUCCESS" if exit_code == 0 else f"FAILED (exit code: {exit_code})")
        return 0

    recent_changes = find_recent_code_changes(Path("."), stall_minutes)
    log_size = log_file.stat().st_size if log_file.exists() else 0

    if recent_changes:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(f"{log_size}\n", encoding="utf-8")
        print("ACTIVE")
        return 0

    last_log_size = 0
    if state_file.exists():
        try:
            last_log_size = int(state_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            last_log_size = 0

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{log_size}\n", encoding="utf-8")
    print("ACTIVE" if log_size > last_log_size else "STALLED")
    return 0


def cmd_summary(task_file: str, report: bool = False) -> int:
    document = read_tasks_document(task_file)
    valid_tasks = report_missing_status(document["tasks"])

    counts = {"OPEN": 0, "IN_PROGRESS": 0, "DONE": 0, "VERIFIED": 0, "REJECTED": 0, "FAILED": 0}
    for task in valid_tasks:
        status = task.get("status")
        if status in counts:
            counts[status] += 1

    total = len(valid_tasks)
    completed = counts["DONE"] + counts["VERIFIED"]
    completion_rate = (completed / total * 100) if total else 0
    audited = counts["VERIFIED"] + counts["REJECTED"]
    audit_rate = (counts["VERIFIED"] / audited * 100) if audited else 0

    lines = [
        f"总任务: {total}",
        f"OPEN: {counts['OPEN']}",
        f"IN_PROGRESS: {counts['IN_PROGRESS']}",
        f"DONE: {counts['DONE']}",
        f"VERIFIED: {counts['VERIFIED']}",
        f"REJECTED: {counts['REJECTED']}",
        f"FAILED: {counts['FAILED']}",
        f"完成率: {completion_rate:.1f}%",
        f"审计通过率: {audit_rate:.1f}%",
    ]
    for line in lines:
        print(line)

    if report:
        report_dir = Path("planning/progress-reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        report_path = report_dir / f"{timestamp}-progress.md"
        report_content = f"# 进度报告\n\n生成时间: {timestamp}\n任务板: {task_file}\n\n"
        report_content += "\n".join(f"- {line}" for line in lines) + "\n"
        atomic_write(report_path, report_content)
        print(f"报告已写入: {report_path}")
    return 0


def register_subparsers(subparsers, *, nested: bool = False):
    if nested:
        # cli.py 直接复用当前 subparsers 定义
        pass

    subparsers.add_parser("init", help="初始化工作环境")

    p_update = subparsers.add_parser("update", help="更新任务状态")
    p_update.add_argument("task_num")
    p_update.add_argument("new_status")
    p_update.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)

    p_select = subparsers.add_parser("select", help="选择下一个可执行任务")
    p_select.add_argument("--parallel", action="store_true")
    p_select.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)

    p_checkpoint_write = subparsers.add_parser("checkpoint-write", help="写入 checkpoint")
    p_checkpoint_write.add_argument("phase")
    p_checkpoint_write.add_argument("extra", nargs="*", default=[])

    subparsers.add_parser("checkpoint-check", help="检查 checkpoint")

    p_detect = subparsers.add_parser("detect", help="检测进程卡死")
    p_detect.add_argument("task_num")
    p_detect.add_argument("pid")
    p_detect.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)

    p_summary = subparsers.add_parser("summary", help="统计进度")
    p_summary.add_argument("--report", action="store_true")
    p_summary.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)


def dispatch(args) -> int:
    if args.command == "init":
        return cmd_init()
    if args.command == "update":
        return cmd_update(args.task_num, args.new_status, args.task_file)
    if args.command == "select":
        return cmd_select(args.parallel, args.task_file)
    if args.command == "checkpoint-write":
        return cmd_checkpoint_write(args.phase, args.extra)
    if args.command == "checkpoint-check":
        return cmd_checkpoint_check()
    if args.command == "detect":
        return cmd_detect(args.task_num, args.pid, args.task_file)
    if args.command == "summary":
        return cmd_summary(args.task_file, report=args.report)
    raise CliError("缺少有效的 task_manager 子命令")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="任务管理核心")
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
