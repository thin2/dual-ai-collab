#!/usr/bin/env python3
"""统一跨平台入口。"""

from __future__ import annotations

import argparse
import sys

import run_task
import task_manager
import verify_task
from tasks_store import CliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dual AI Collaboration 跨平台入口")
    subparsers = parser.add_subparsers(dest="command")
    task_manager.register_subparsers(subparsers, nested=True)
    run_task.register_subparsers(subparsers, nested=True)
    verify_task.register_subparsers(subparsers, nested=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command in {"init", "update", "select", "checkpoint-write", "checkpoint-check", "detect", "summary"}:
            raise SystemExit(task_manager.dispatch(args))
        if args.command == "run":
            raise SystemExit(run_task.dispatch(args))
        if args.command == "verify":
            raise SystemExit(verify_task.dispatch(args))
        parser.print_help()
        raise SystemExit(1)
    except CliError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
