#!/usr/bin/env python3
"""Planning-only entry point backed by the local Dual AI Collaboration checkout."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys

COMMANDS = {
    "init", "update", "select", "checkpoint-write", "checkpoint-check",
    "summary", "board", "templates", "visualize", "analyze", "verify",
}


def main() -> None:
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help"}:
        print("规划与任务板（当前会话执行，不启动模型 CLI）\n命令: " + ", ".join(sorted(COMMANDS)))
        print("每条命令可加 --help。请在目标项目根目录执行。")
        return
    if sys.argv[1] not in COMMANDS:
        sys.exit("此入口只提供规划、任务板和验收，不提供 run 或适配器命令。")
    skill = Path(__file__).resolve().parents[1]
    config = skill / "source.json"
    repository = (Path(json.loads(config.read_text(encoding="utf-8"))["repository"])
                  if config.exists() else skill.parents[1])
    scripts = repository / "skill" / "scripts"
    if not (scripts / "cli.py").is_file():
        sys.exit("本地项目已移动或缺失，请从新位置重新安装 planning 技能。")
    # Keep the caller's cwd: project task data must never enter the skill directory.
    sys.path.insert(0, str(scripts))
    runpy.run_path(str(scripts / "cli.py"), run_name="__main__")


if __name__ == "__main__":
    main()
