#!/usr/bin/env python3
"""verify_task.py - 从任务板提取并执行任务验收标准中的可执行命令。"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def _read_task_block(task_num: str, task_file: Path) -> list[str]:
    if not task_file.exists():
        print(f"ERROR: 任务板不存在: {task_file}", file=sys.stderr)
        sys.exit(1)

    lines = task_file.read_text(encoding="utf-8").splitlines()
    block: list[str] = []
    in_task = False

    for line in lines:
        if re.match(r"^## 任务 #0*" + re.escape(task_num.lstrip("0")) + r":", line):
            in_task = True
            block.append(line)
            continue
        if in_task and line.strip() == "---":
            break
        if in_task:
            block.append(line)

    if not block:
        print(f"ERROR: 未找到任务 #{task_num}", file=sys.stderr)
        sys.exit(1)

    return block


def _extract_verification_commands(task_num: str, task_file: Path) -> list[str]:
    block = _read_task_block(task_num, task_file)
    commands: list[str] = []
    in_acceptance = False

    for line in block[1:]:
        if re.match(r"^### 验收标准", line):
            in_acceptance = True
            continue
        if in_acceptance and re.match(r"^### ", line):
            break

        if not in_acceptance:
            continue

        match = re.search(r"`([^`]+)`", line)
        if match:
            commands.append(match.group(1).strip())

    return commands


def cmd_extract(task_num: str, task_file: str) -> int:
    commands = _extract_verification_commands(task_num, Path(task_file))
    if not commands:
        print(f"NO_VERIFICATION_COMMANDS: 任务 #{task_num} 未定义可执行验收命令", file=sys.stderr)
        return 2

    for command in commands:
        print(command)
    return 0


def cmd_run(task_num: str, task_file: str, workdir: str) -> int:
    commands = _extract_verification_commands(task_num, Path(task_file))
    if not commands:
        print(f"NO_VERIFICATION_COMMANDS: 任务 #{task_num} 未定义可执行验收命令", file=sys.stderr)
        return 2

    for index, command in enumerate(commands, start=1):
        print(f"VERIFY[{index}/{len(commands)}]: {command}")
        result = subprocess.run(["bash", "-lc", command], cwd=workdir)
        if result.returncode != 0:
            print(
                f"VERIFY_FAILED: 任务 #{task_num} 的验收命令 #{index} 失败（exit code: {result.returncode}）",
                file=sys.stderr,
            )
            return result.returncode or 1

    print(f"VERIFY_PASSED: 任务 #{task_num} 的 {len(commands)} 条验收命令全部通过")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="提取并运行任务验收命令")
    sub = parser.add_subparsers(dest="command")

    p_extract = sub.add_parser("extract", help="提取可执行验收命令")
    p_extract.add_argument("task_num", help="任务编号")
    p_extract.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")

    p_run = sub.add_parser("run", help="运行可执行验收命令")
    p_run.add_argument("task_num", help="任务编号")
    p_run.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")
    p_run.add_argument("--workdir", default=".", help="命令执行目录（默认：当前目录）")

    args = parser.parse_args()

    if args.command == "extract":
        raise SystemExit(cmd_extract(args.task_num, args.task_file))
    if args.command == "run":
        raise SystemExit(cmd_run(args.task_num, args.task_file, args.workdir))

    parser.print_help()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
