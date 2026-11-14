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



def verify_report(commands: list[str], workdir: str, timeout: float = 120) -> dict:
    """Persistable acceptance evidence with bounded output and process cleanup."""
    import math
    import os
    import shutil
    import subprocess
    import tempfile
    import time
    from platform_utils import terminate_process_tree

    try:
        timeout = float(timeout)
    except (ValueError, TypeError) as exc:
        raise CliError('verification_timeout 必须为正数') from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise CliError('verification_timeout 必须为正数')
    report = {'passed': False, 'commands': [], 'reason': None}
    if not commands:
        report['reason'] = '没有可执行的验收命令，不能标记 DONE'
        return report
    for command in commands:
        started = time.monotonic()
        timed_out = False
        shell = shutil.which('bash') or shutil.which('sh')
        argv = command if os.name == 'nt' else [shell or '/bin/sh', '-c', command]
        kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        with tempfile.TemporaryFile() as output:
            try:
                proc = subprocess.Popen(argv, cwd=workdir, shell=os.name == 'nt',
                                        stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kwargs)
                try:
                    code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate_process_tree(proc.pid, force=True)
                    proc.wait(timeout=5)
                    code = 124
                except BaseException:
                    terminate_process_tree(proc.pid, force=True)
                    proc.wait(timeout=5)
                    raise
            except OSError as exc:
                code = 127
                output.write(str(exc).encode())
            size = output.seek(0, os.SEEK_END)
            output.seek(max(0, size - 16000))
            text = output.read().decode('utf-8', errors='replace')
        report['commands'].append({'command': command, 'exit_code': code, 'output': text,
                                   'output_truncated': size > 16000, 'timed_out': timed_out,
                                   'duration_seconds': time.monotonic() - started})
        if code:
            report['reason'] = '验收超时' if timed_out else '验收命令失败'
            return report
    report['passed'] = True
    return report


if __name__ == "__main__":
    main()
