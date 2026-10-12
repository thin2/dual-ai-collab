#!/usr/bin/env python3
"""Checkpoint 管理 - 简化版。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .store import atomic_write
except ImportError:
    from store import atomic_write


class CheckpointManager:
    """Checkpoint 管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.checkpoint_file = project_root / ".task-management" / "checkpoint.json"

    def save(self, phase: str, **data: Any) -> None:
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
        """加载 checkpoint"""
        if not self.checkpoint_file.exists():
            return None
        
        try:
            return json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

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
