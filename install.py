#!/usr/bin/env python3
"""Cross-platform installer for the Dual AI Collaboration skill."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        relative = path.relative_to(src)
        target = dst / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(path, target)


def install(target_dir: Path, source_root: Path, force: bool) -> None:
    skill_root = source_root / "skill"
    skill_file = skill_root / "dual-ai-collab.md"
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
    copy_file(skill_file, target_dir / "dual-ai-collab.md")
    copy_tree(scripts_dir, target_dir / "scripts")
    copy_tree(references_dir, target_dir / "references")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the Dual AI Collaboration skill")
    parser.add_argument(
        "--target",
        default="~/.claude/skills/dual-ai-collab",
        help="安装目录（默认：~/.claude/skills/dual-ai-collab）",
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
    target_dir = Path(args.target).expanduser().resolve()

    try:
        install(target_dir, source_root, force=args.force)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print("INSTALL_OK")
    print(f"source: {source_root}")
    print(f"target: {target_dir}")
    print("已安装 dual-ai-collab skill，包括主文件、scripts/ 和 references/。")


if __name__ == "__main__":
    main()
