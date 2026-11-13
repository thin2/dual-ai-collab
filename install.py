#!/usr/bin/env python3
"""Installer for the foreman skill (macOS and Linux) and the legacy dual-ai-collab skill."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> list[str]:
    """Copy src into dst and return the files copied, as paths relative to dst."""
    if not src.exists():
        raise FileNotFoundError(src)
    dst.mkdir(parents=True, exist_ok=True)
    skip_dirs = {"__pycache__", ".mypy_cache"}
    copied = []
    for path in src.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        relative = path.relative_to(src)
        target = dst / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(path, target)
            copied.append(relative.as_posix())
    return copied


LAUNCHER = Path("bin") / "foreman"
# The files an install put in the skill folder, so the next install can tell its own leftovers from other files.
MANIFEST = ".install-manifest.json"


def recorded_files(target_dir: Path) -> list[str] | None:
    """The files the last install recorded putting in target_dir; None when it left no usable record."""
    try:
        files = json.loads((target_dir / MANIFEST).read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
        return None
    return files


def _remove_while_empty(folder: Path, root: Path) -> None:
    while folder != root and root in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def remove_stale(target_dir: Path, recorded: list[str], files: list[str]) -> list[str]:
    """Delete the files an earlier install put in target_dir that this version does not ship; return their names.

    Only files that install recorded are candidates, so anything else in the folder is left alone.
    """
    root = target_dir.resolve()
    shipped = [root / name for name in files]
    removed = []
    for name in sorted(set(recorded) - set(files)):
        folder = (root / name).parent.resolve()
        path = folder / Path(name).name
        # The record is an editable file: a damaged one must not point this at anything outside the skill folder.
        if folder != root and root not in folder.parents:
            continue
        # A name that differs only in case from a shipped one is the same file on macOS.
        if not path.is_file() or any(path.samefile(other) for other in shipped):
            continue
        path.unlink()
        removed.append(name)
        cache = folder / "__pycache__"
        if path.suffix == ".py" and cache.is_dir():
            for compiled in cache.glob(f"{path.stem}.*.pyc"):
                compiled.unlink()
            _remove_while_empty(cache, root)
        _remove_while_empty(folder, root)
    return removed


def check_platform(profile: str) -> None:
    """Refuse to install foreman where it cannot run: it locks files with fcntl and manages POSIX process groups."""
    if profile == "foreman" and sys.platform == "win32":
        raise RuntimeError(
            "foreman 只支持 macOS 和 Linux；Windows 上请在 WSL 里运行这个安装脚本。"
            "旧版 dual-ai-collab 仍可用 --profile full 安装。\n"
            "foreman runs on macOS and Linux only. On Windows, run this installer inside WSL; "
            "the legacy skill still installs with --profile full."
        )


def skill_version(skill_dir: Path) -> str | None:
    """The version in a skill's SKILL.md frontmatter; None when the file or the field is missing."""
    try:
        frontmatter = (skill_dir / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, ValueError, IndexError):
        return None
    for line in frontmatter.splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _is_foreman_launcher(path: Path) -> bool:
    skill = path.parent.parent
    return path.name == "foreman" and (skill / "SKILL.md").is_file() and (skill / "tools" / "cli.py").is_file()


def check_link(link: Path) -> None:
    """Refuse to replace anything except a dangling link or a link to a foreman launcher.

    Other programs are also called foreman (the Ruby Procfile runner, for one).
    """
    if not link.is_symlink() and not link.exists():
        return
    if not link.is_symlink() or (link.exists() and not _is_foreman_launcher(link.resolve())):
        raise RuntimeError(f"{link} 已存在，而且不是 foreman 技能的链接；换一个 --bin-dir，或确认不需要后自己删除它")


def link_launcher(launcher: Path, link: Path) -> None:
    check_link(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        link.unlink()
    link.symlink_to(launcher)


def launcher_notes(launcher: Path, link: Path | None) -> list[str]:
    """What to type to run the installed skill, given what `foreman` resolves to on PATH."""
    found = shutil.which("foreman")
    on_path = bool(found) and Path(found).resolve() == launcher.resolve()
    notes = [f"command: {'foreman' if on_path else launcher}"]
    if link:
        notes.append(f"link: {link} -> {launcher}")
    if on_path:
        return notes
    if found:
        notes.append(f"提示：PATH 里的 foreman 是另一个程序（{found}）；使用上面的完整路径，或调整 PATH 的顺序")
    elif link:
        notes.append(f"提示：{link.parent} 不在 PATH 里；加入 PATH 后可以直接输入 foreman，在那之前使用上面的完整路径")
    else:
        notes.append("提示：想直接输入 foreman，加 --force --bin-dir <PATH 里的目录>（例如 ~/.local/bin）重新安装")
    return notes


def install(target_dir: Path, source_root: Path, force: bool, profile: str = "full") -> list[str]:
    """Install the skill; return what to tell the user about files an earlier install left in target_dir."""
    if profile not in {"full", "foreman"}:
        raise ValueError(f"Unknown profile: {profile}")

    # Foreman profile (Droid native). It carries its own code, so the
    # installed copy keeps working when this repository is moved or deleted.
    if profile == "foreman":
        source = source_root / "foreman"
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError(source / "SKILL.md")
        if target_dir.exists() and any(target_dir.iterdir()) and not force:
            raise RuntimeError(f"目标目录已存在且非空: {target_dir}；覆盖需 --force")
        replacing = (target_dir / "SKILL.md").is_file()
        recorded = recorded_files(target_dir)
        files = sorted(name for name in copy_tree(source, target_dir) if name != MANIFEST)
        # The source may come from an archive or a filesystem that dropped the mode bits.
        (target_dir / LAUNCHER).chmod(0o755)
        notes = []
        if recorded is not None:
            removed = remove_stale(target_dir, recorded, files)
            if removed:
                notes.append(f"removed: {'、'.join(removed)}（上一版本安装的文件，这个版本不再包含）")
        elif replacing:
            notes.append("提示：上一次安装没有留下文件清单，这次没有清理旧文件；"
                         "从这个版本起，重新安装会删除新版本不再包含的文件")
        (target_dir / MANIFEST).write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
        print("提示：规划、任务板和当前会话直接执行可立即使用；派发给固定模型角色需要 Droid")
        return notes

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
    copy_file(skill_file, target_dir / "SKILL.md")
    copy_tree(scripts_dir, target_dir / "scripts")
    copy_tree(references_dir, target_dir / "references")
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the Dual AI Collaboration skill")
    parser.add_argument(
        "--target",
        default=None,
        help="安装目录（默认：foreman 安装到 Droid，full 安装到 Claude）",
    )
    parser.add_argument(
        "--source",
        default=".",
        help="仓库根目录（默认：当前目录）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的安装目录内容；foreman 还会删除上一版本安装过、这个版本不再包含的文件",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "foreman"),
        default="foreman",
        help="foreman: 规划、任务板和执行管理 (默认，已包含原 planning 技能), full: 旧版 dual-ai-collab"
    )
    parser.add_argument(
        "--bin-dir",
        default=None,
        help="只用于 foreman：在这个目录创建 foreman 命令的链接（目录应在 PATH 里，例如 ~/.local/bin）",
    )
    args = parser.parse_args()
    if args.bin_dir and args.profile != "foreman":
        parser.error("--bin-dir 只用于 --profile foreman")

    source_root = Path(args.source).expanduser().resolve()

    # 确定默认安装路径
    if args.profile == "foreman":
        default_target = Path(os.environ.get("FACTORY_SKILLS") or "~/.factory/skills") / "foreman"
    else:
        default_target = Path("~/.claude/skills/dual-ai-collab")

    target_dir = Path(args.target or default_target).expanduser().resolve()
    # Only the directory is resolved: the link itself may already exist and must not be followed.
    link = Path(args.bin_dir).expanduser().resolve() / "foreman" if args.bin_dir else None

    replacing = (target_dir / "SKILL.md").is_file()
    previous = skill_version(target_dir)
    try:
        check_platform(args.profile)
        if link:
            check_link(link)  # before copying, so a refused link leaves nothing half installed
        notes = install(target_dir, source_root, force=args.force, profile=args.profile)
        if link:
            link_launcher(target_dir / LAUNCHER, link)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    print("INSTALL_OK")
    print(f"source: {source_root}")
    print(f"target: {target_dir}")
    if args.profile == "foreman":
        replaced = ""
        if replacing:
            replaced = f"（替换了 {previous}）" if previous else "（替换了没有版本号的旧版）"
        print(f"version: {skill_version(target_dir) or '未标注'}{replaced}")
        print("\n".join(notes + launcher_notes(target_dir / LAUNCHER, link)))


if __name__ == "__main__":
    main()
