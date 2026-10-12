#!/usr/bin/env python3
"""任务执行器 - 准备任务执行计划。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .board import TaskBoard
    from .config import ExecutionConfig
except ImportError:
    from board import TaskBoard
    from config import ExecutionConfig


class TaskExecutor:
    """任务执行器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.board = TaskBoard.load(project_root)
        self.config = ExecutionConfig(project_root)

    def plan_execution(self, task_id: str) -> dict[str, Any]:
        """
        规划任务执行
        
        返回执行计划，包含：
        - task_id: 任务编号
        - complexity: 复杂度 (light/medium/heavy)
        - droid: 要使用的 droid 名称
        - context: 执行上下文
        """
        task = self.board.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # 确定复杂度
        complexity = self.config.determine_complexity(task)

        # 获取对应的 droid
        droid = self.config.get_droid_for_complexity(complexity)

        # 构建上下文
        context = self.board.build_context(task)

        return {
            "task_id": task_id,
            "task_title": task.get("title", ""),
            "complexity": complexity,
            "droid": droid,
            "context": context,
            "task_type": task.get("type", "feature"),
            "estimated_hours": task.get("estimated_hours", 0),
        }

    def get_execution_info(self, task_id: str) -> str:
        """获取任务执行信息的文本描述"""
        plan = self.plan_execution(task_id)
        
        lines = [
            f"任务: {plan['task_id']} - {plan['task_title']}",
            f"类型: {plan['task_type']}",
            f"预估时间: {plan['estimated_hours']}小时",
            f"→ 复杂度: {plan['complexity']}",
            f"→ 使用 Droid: {plan['droid']}",
        ]
        
        return "\n".join(lines)
