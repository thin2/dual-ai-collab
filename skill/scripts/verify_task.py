#!/usr/bin/env python3
"""verify_task.py - 从任务存储中提取并执行验收命令。"""

from __future__ import annotations

import argparse
import sys

from platform_utils import run_command
from tasks_store import CliError, DEFAULT_TASKS_MD, extract_acceptance_commands, find_task, read_tasks_document


def _commands_for_task(task_num: str, task_file: str) -> list[str]:
    document = read_tasks_document(task_file)
    task = find_task(document, task_num)
    if task is None:
        raise CliError(f"未找到任务 #{task_num}")
    return extract_acceptance_commands(task)


def cmd_extract(task_num: str, task_file: str) -> int:
    commands = _commands_for_task(task_num, task_file)
    if not commands:
        print(f"NO_VERIFICATION_COMMANDS: 任务 #{task_num} 未定义可执行验收命令", file=sys.stderr)
        return 2
    for command in commands:
        print(command)
    return 0


def cmd_run(task_num: str, task_file: str, workdir: str) -> int:
    commands = _commands_for_task(task_num, task_file)
    if not commands:
        print(f"NO_VERIFICATION_COMMANDS: 任务 #{task_num} 未定义可执行验收命令", file=sys.stderr)
        return 2

    for index, command in enumerate(commands, start=1):
        print(f"VERIFY[{index}/{len(commands)}]: {command}")
        try:
            result = run_command(command, cwd=workdir)
        except RuntimeError as exc:
            print(f"VERIFY_FAILED: {exc}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            print(
                f"VERIFY_FAILED: 任务 #{task_num} 的验收命令 #{index} 失败（exit code: {result.returncode}）",
                file=sys.stderr,
            )
            return result.returncode or 1

    print(f"VERIFY_PASSED: 任务 #{task_num} 的 {len(commands)} 条验收命令全部通过")
    return 0


def register_subparsers(subparsers, *, nested: bool = False):
    target = subparsers.add_parser("verify", help="验收命令") if nested else None
    verify_sub = target.add_subparsers(dest="verify_command") if nested else subparsers

    p_extract = verify_sub.add_parser("extract", help="提取可执行验收命令")
    p_extract.add_argument("task_num")
    p_extract.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)

    p_run = verify_sub.add_parser("run", help="运行可执行验收命令")
    p_run.add_argument("task_num")
    p_run.add_argument("task_file", nargs="?", default=DEFAULT_TASKS_MD)
    p_run.add_argument("--workdir", default=".")


def dispatch(args) -> int:
    if getattr(args, "verify_command", None) == "extract" or getattr(args, "command", None) == "extract":
        return cmd_extract(args.task_num, args.task_file)
    if getattr(args, "verify_command", None) == "run" or getattr(args, "command", None) == "run":
        return cmd_run(args.task_num, args.task_file, args.workdir)
    raise CliError("缺少有效的 verify 子命令")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="提取并运行任务验收命令")
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
