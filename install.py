#!/usr/bin/env python3
"""Cross-platform installer for the Dual AI Collaboration skill."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL_CONFIGS = {
    "dual": {
        "source_dir": "skill",
        "skill_file": "dual-ai-collab.md",
        "default_target": "~/.claude/skills/dual-ai-collab",
        "label": "dual-ai-collab",
    },
    "planning": {
        "source_dir": "planning-skill",
        "skill_file": "planning-collab.md",
        "default_target": "~/.claude/skills/planning-collab",
        "label": "planning-collab",
    },
}


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.mkdir(parents=True, exist_ok=True)
    skip_dirs = {"__pycache__", ".mypy_cache"}
    for path in src.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        relative = path.relative_to(src)
        target = dst / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(path, target)


def install(target_dir: Path, source_root: Path, config: dict, force: bool) -> None:
    skill_root = source_root / config["source_dir"]
    skill_file = skill_root / config["skill_file"]
    scripts_dir = skill_root / "scripts"
    references_dir = skill_root / "references"

    if not skill_file.exists():
        raise FileNotFoundError(skill_file)

    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        raise RuntimeError(
            f"目标目录已存在且非空: {target_dir}\n"
            "如需覆盖，请重新运行并加上 --force。"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    copy_file(skill_file, target_dir / config["skill_file"])
    if scripts_dir.exists():
        copy_tree(scripts_dir, target_dir / "scripts")
    if references_dir.exists():
        copy_tree(references_dir, target_dir / "references")


def _install_one(skill_name: str, source_root: Path, target_override: str | None, force: bool) -> None:
    config = SKILL_CONFIGS[skill_name]
    if target_override:
        target_dir = Path(target_override).expanduser().resolve()
    else:
        target_dir = Path(config["default_target"]).expanduser().resolve()

    install(target_dir, source_root, config, force=force)
    print(f"INSTALL_OK: {config['label']}")
    print(f"  target: {target_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the Dual AI Collaboration skill")
    parser.add_argument(
        "--skill",
        default="both",
        choices=["dual", "planning", "both"],
        help="安装哪个技能（默认：both，同时安装两个）",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="安装目录（--skill both 时忽略此参数）",
    )
    parser.add_argument(
        "--source",
        default=".",
        help="仓库根目录（默认：当前目录）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的安装目录内容",
    )
    args = parser.parse_args()

    source_root = Path(args.source).expanduser().resolve()
    skills = ["dual", "planning"] if args.skill == "both" else [args.skill]

    try:
        for skill_name in skills:
            target = None if args.skill == "both" else args.target
            _install_one(skill_name, source_root, target, force=args.force)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"source: {source_root}")


if __name__ == "__main__":
    main()
