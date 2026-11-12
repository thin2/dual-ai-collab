#!/usr/bin/env python3
"""Checkpoint 管理 - 简化版。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .store import atomic_write, describe_error
except ImportError:
    from store import atomic_write, describe_error


class CheckpointError(ValueError):
    """checkpoint 文件存在，但内容不能用"""


class CheckpointManager:
    """Checkpoint 管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.checkpoint_file = project_root / ".task-management" / "checkpoint.json"
        self.set_aside_file = self.checkpoint_file.with_name("checkpoint.json.corrupted")

    def save(self, phase: str, /, **data: Any) -> None:
        """
        保存 checkpoint

        Args:
            phase: 当前阶段 (planning, developing, reviewing)
            **data: 额外数据
        """
        checkpoint = {
            "phase": phase,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n"
        atomic_write(self.checkpoint_file, content)

    def load(self) -> dict | None:
        """加载 checkpoint；没有文件时返回 None，文件读不出来时报错"""
        if not self.checkpoint_file.exists():
            return None

        try:
            checkpoint = json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CheckpointError(self._unusable(describe_error(error))) from error
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("data", {}), dict):
            raise CheckpointError(self._unusable("内容和其中的 data 都应是 JSON 对象"))
        return checkpoint

    def _unusable(self, reason: str) -> str:
        return (f"checkpoint 文件 {self.checkpoint_file} 无法使用（{reason}）。任务板和执行记录不受影响；"
                f"运行 foreman execution sync 按任务板重建进度，原文件会另存为 {self.set_aside_file.name}")

    def set_aside(self) -> Path:
        """把读不出来的 checkpoint 挪到一边，留给用户找回里面的内容"""
        self.checkpoint_file.replace(self.set_aside_file)
        return self.set_aside_file

    def check(self) -> str:
        """检查 checkpoint 状态"""
        checkpoint = self.load()

        if not checkpoint:
            return "NO_CHECKPOINT"

        phase = checkpoint.get("phase", "unknown")
        data = checkpoint.get("data", {})

        lines = [
            "CHECKPOINT_FOUND",
            f"Phase: {phase}",
            f"Time: {checkpoint.get('timestamp', 'unknown')}",
        ]

        for key, value in data.items():
            lines.append(f"{key}: {value}")

        return "\n".join(lines)

    def clear(self) -> None:
        """清除 checkpoint"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
