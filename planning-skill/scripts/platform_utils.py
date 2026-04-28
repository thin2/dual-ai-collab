#!/usr/bin/env python3
"""跨平台辅助函数：文件锁。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    import fcntl  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Windows only
    fcntl = None

try:
    import msvcrt  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - POSIX only
    msvcrt = None

IS_WINDOWS = os.name == "nt"


class FileLock:
    """基于 lock file 的简单跨平台排他锁。"""

    def __init__(self, lock_path: Path, timeout: float = 10.0, stale_after: float = 60.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.stale_after = stale_after
        self._fd: int | None = None
        self._uses_native_lock = bool(fcntl is not None or msvcrt is not None)

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout

        if self._uses_native_lock:
            return self._enter_native(deadline)

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
                if self._break_stale_lock():
                    continue
                if time.time() >= deadline:
                    raise TimeoutError(f"获取锁超时: {self.lock_path}")
                time.sleep(0.1)

    def __exit__(self, *exc):
        if self._uses_native_lock:
            self._exit_native()
            return False

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

    def _break_stale_lock(self) -> bool:
        try:
            stat_before = self.lock_path.stat()
        except FileNotFoundError:
            return True
        if time.time() - stat_before.st_mtime < self.stale_after:
            return False

        try:
            fd = os.open(self.lock_path, os.O_RDONLY)
        except FileNotFoundError:
            return True
        except OSError:
            return False

        try:
            stat_open = os.fstat(fd)
        finally:
            os.close(fd)

        try:
            stat_now = self.lock_path.stat()
        except FileNotFoundError:
            return True

        signature_before = (stat_before.st_dev, stat_before.st_ino, stat_before.st_mtime_ns, stat_before.st_size)
        signature_open = (stat_open.st_dev, stat_open.st_ino, stat_open.st_mtime_ns, stat_open.st_size)
        signature_now = (stat_now.st_dev, stat_now.st_ino, stat_now.st_mtime_ns, stat_now.st_size)
        if signature_before != signature_now or signature_open != signature_now:
            return False

        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def _enter_native(self, deadline: float):
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                elif msvcrt is not None:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover
                    break
                self._write_lock_metadata()
                return self
            except (BlockingIOError, OSError):
                if time.time() >= deadline:
                    os.close(self._fd)
                    self._fd = None
                    raise TimeoutError(f"获取锁超时: {self.lock_path}")
                time.sleep(0.1)

    def _exit_native(self) -> None:
        if self._fd is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            elif msvcrt is not None:
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self._fd)
            self._fd = None

    def _write_lock_metadata(self) -> None:
        if self._fd is None:
            return
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, str(os.getpid()).encode("utf-8"))
        os.fsync(self._fd)
