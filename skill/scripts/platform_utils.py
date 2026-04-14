#!/usr/bin/env python3
"""跨平台辅助函数：文件锁、进程管理、shell 执行、文件扫描。"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def default_python() -> str:
    return sys.executable or ("python" if IS_WINDOWS else "python3")


class FileLock:
    """基于 lock file 的简单跨平台排他锁。"""

    def __init__(self, lock_path: Path, timeout: float = 10.0, stale_after: float = 60.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.stale_after = stale_after
        self._fd: int | None = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout

        while True:
            try:
                self._fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                os.write(self._fd, str(os.getpid()).encode("utf-8"))
                return self
            except FileExistsError:
                if self._is_stale():
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.time() >= deadline:
                    raise TimeoutError(f"获取锁超时: {self.lock_path}")
                time.sleep(0.1)

    def __exit__(self, *exc):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        return False

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except FileNotFoundError:
            return False
        return age >= self.stale_after


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False

    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    output = result.stdout.strip()
    if not output or "No tasks are running" in output:
        return False
    return f'"{pid}"' in output or f",{pid}," in output


def terminate_process_tree(pid: int, force: bool = False) -> None:
    if pid <= 0:
        return

    if IS_WINDOWS:
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            cmd.append("/F")
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        return

    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(pid, sig)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            pass


def wait_for_process_exit(pid: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not is_process_running(pid):
            return True
        time.sleep(0.1)
    return not is_process_running(pid)


def find_recent_code_changes(root: Path, minutes: int) -> list[str]:
    cutoff = time.time() - minutes * 60
    matches: list[str] = []
    code_exts = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
        ".java", ".c", ".cpp", ".vue", ".svelte", ".html", ".css",
    }
    ignored_dirs = {"node_modules", ".git", ".venv", "venv", "__pycache__"}

    def walk(path: Path) -> None:
        nonlocal matches
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if len(matches) >= 5:
                        return
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in ignored_dirs:
                            continue
                        walk(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if Path(entry.name).suffix not in code_exts:
                        continue
                    try:
                        if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                            matches.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            return

    walk(root)

    return matches


def has_command(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(command: str, cwd: str, check: bool = False) -> subprocess.CompletedProcess:
    """按平台选择 shell，兼容 bash 显式命令和普通跨平台命令。"""
    stripped = command.strip()

    if stripped.startswith("bash "):
        if not has_command("bash"):
            raise RuntimeError("当前环境缺少 bash，无法执行 `bash ...` 命令。请改用跨平台命令或安装 Git Bash/WSL。")
        return subprocess.run(["bash", "-lc", stripped], cwd=cwd, check=check)

    if stripped.startswith("sh "):
        if not has_command("sh"):
            raise RuntimeError("当前环境缺少 sh，无法执行 `sh ...` 命令。")
        return subprocess.run(["sh", "-lc", stripped], cwd=cwd, check=check)

    if IS_WINDOWS:
        return subprocess.run(stripped, cwd=cwd, shell=True, check=check)

    shell = "bash" if has_command("bash") else "sh"
    return subprocess.run([shell, "-lc", stripped], cwd=cwd, check=check)
