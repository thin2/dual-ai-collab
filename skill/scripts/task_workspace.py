"""Optional Git worktrees. Never stash, commit, merge, or remove user changes."""
from __future__ import annotations

from pathlib import Path
import subprocess

from tasks_store import CliError


def git(cwd, *args):
    try:
        result = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CliError(f'Git 操作失败: {exc}') from exc
    if result.returncode:
        raise CliError(result.stderr.strip() or 'Git 操作失败')
    return result.stdout.strip()


def create_worktree(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    root = Path(git(source, 'rev-parse', '--show-toplevel')).resolve()
    if root != source:
        raise CliError('--isolate 的 --workdir 必须是 Git 仓库根目录')
    if git(source, 'status', '--porcelain', '--untracked-files=normal'):
        raise CliError('创建隔离 worktree 需要干净的工作区；请先处理改动，或不使用 --isolate')
    base = git(source, 'rev-parse', 'HEAD')
    target.parent.mkdir(parents=True, exist_ok=True)
    git(source, 'worktree', 'add', '--detach', str(target), base)
    return {'workdir': str(target), 'source_workdir': str(source), 'base_commit': base,
            'isolated': True}
