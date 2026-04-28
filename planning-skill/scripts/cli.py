#!/usr/bin/env python3
"""planning-collab 统一入口。"""

from __future__ import annotations

import argparse
import sys

import task_manager
from tasks_store import CliError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Planning Collaboration 跨平台入口")
    subparsers = parser.add_subparsers(dest="command")
    task_manager.register_subparsers(subparsers, nested=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command in {
            "init", "update", "select",
            "checkpoint-write", "checkpoint-check", "summary",
        }:
            raise SystemExit(task_manager.dispatch(args))
        parser.print_help()
        raise SystemExit(1)
    except CliError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
