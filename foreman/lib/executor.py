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

    def _plan(self, task: dict) -> dict[str, Any]:
        task_id = task["id"]
        complexity = self.config.determine_complexity(task)
        context = self.board.build_context(task)
        description = f"任务 {task_id}: {task.get('title', '')}".strip()
        role = task.get("role")

        if role:
            entry = self.config.get_role(role)
            if not entry:
                raise ValueError(
                    f"任务 {task_id} 的角色 {role} 未配置；先运行 foreman team set {role} --model <模型ID> --description <职责>"
                )
            droid = entry["droid"]
            model = entry.get("model")
            # 固定模型的 droid 不受 complexity 路由影响，传了也会被忽略，因此不传
            task_args = {"subagent_type": droid, "description": description, "prompt": context}
        else:
            droid = self.config.get_droid_for_complexity(complexity)
            model = None
            task_args = {
                "subagent_type": droid,
                "description": description,
                "prompt": context,
                "complexity": complexity,
            }

        return {
            "task_id": task_id,
            "task_title": task.get("title", ""),
            # 写了 role 的任务派给固定模型的角色；没写的由当前会话自己完成
            "mode": "dispatch" if role else "direct",
            "role": role,
            "complexity": complexity,
            "droid": droid,
            "model": model,
            "files": list(task.get("files") or []),
            "context": context,
            "task_type": task.get("type", "feature"),
            "estimated_hours": task.get("estimated_hours", 0),
            "task_args": task_args,
        }

    def plan_execution(self, task_id: str) -> dict[str, Any]:
        """
        规划单个任务的执行

        返回执行计划，包含 task_id、role、complexity、droid、model、context，
        以及可直接用于 Task 工具调用的 task_args。
        """
        task = self.board.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        return self._plan(task)

    def plan_batch(self) -> dict[str, Any]:
        """规划下一批可并行执行的任务"""
        selection = self.board.select_batch(self.config.get_roles(), self.config.get_max_parallel())
        return {
            "batch": [self._plan(task) for task in selection["batch"]],
            "skipped": selection["skipped"],
            "max_parallel": selection["max_parallel"],
        }

    def get_execution_info(self, task_id: str) -> str:
        """获取任务执行信息的文本描述"""
        plan = self.plan_execution(task_id)

        lines = [
            f"任务: {plan['task_id']} - {plan['task_title']}",
            f"类型: {plan['task_type']}",
            f"预估时间: {plan['estimated_hours']}小时",
        ]
        if plan["role"]:
            lines.append(f"→ 角色: {plan['role']}")
            lines.append(f"→ 使用 Droid: {plan['droid']}（固定模型 {plan['model']}）")
        else:
            lines.append("→ 没有 role：由当前会话直接执行")
            lines.append(f"→ 复杂度: {plan['complexity']}")
            lines.append(f"→ 需要通用子 Agent 帮忙时可用 Droid: {plan['droid']}（不固定模型）")

        return "\n".join(lines)
