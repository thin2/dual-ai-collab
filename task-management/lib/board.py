#!/usr/bin/env python3
"""任务板核心逻辑 - 简化版，专注于任务管理。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .store import (
        read_tasks_document,
        write_tasks_document,
        find_task,
        executable_tasks,
        open_tasks_sorted,
        extract_acceptance_commands,
    )
except ImportError:
    from store import (
        read_tasks_document,
        write_tasks_document,
        find_task,
        executable_tasks,
        open_tasks_sorted,
        extract_acceptance_commands,
    )


class TaskBoard:
    """任务板管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.task_file = project_root / "planning" / "codex-tasks.md"

    @classmethod
    def load(cls, project_root: Path | str) -> TaskBoard:
        """加载任务板"""
        return cls(Path(project_root))

    def get_document(self) -> dict:
        """获取完整的任务文档"""
        return read_tasks_document(self.task_file)

    def save_document(self, document: dict) -> None:
        """保存任务文档"""
        write_tasks_document(document, self.task_file)

    def get_task(self, task_id: str) -> dict | None:
        """获取单个任务"""
        document = self.get_document()
        return find_task(document, task_id)

    def update_task_status(self, task_id: str, status: str) -> None:
        """更新任务状态"""
        document = self.get_document()
        task = find_task(document, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task["status"] = status
        self.save_document(document)

    def get_next_task(self) -> dict | None:
        """获取下一个可执行的任务"""
        document = self.get_document()
        tasks = executable_tasks(document)
        if not tasks:
            return None
        return tasks[0]

    def get_all_tasks(self) -> list[dict]:
        """获取所有任务"""
        document = self.get_document()
        return document.get("tasks", [])

    def get_open_tasks(self) -> list[dict]:
        """获取所有未完成的任务（按优先级排序）"""
        document = self.get_document()
        return open_tasks_sorted(document)

    def get_acceptance_commands(self, task_id: str) -> list[str]:
        """获取任务的验收命令"""
        task = self.get_task(task_id)
        if not task:
            return []
        return extract_acceptance_commands(task)

    def build_context(self, task: dict) -> str:
        """为子 agent 构建执行上下文"""
        sections = []

        # 任务基本信息
        sections.append(f"# 任务 {task['id']}: {task.get('title', '未命名任务')}")
        sections.append("")

        # 任务描述
        if "description" in task:
            sections.append("## 任务描述")
            sections.append(task["description"])
            sections.append("")

        # 约束条件
        constraints = []
        for section in task.get("sections", []):
            if section.get("heading") in ["约束", "注意事项", "技术要求"]:
                constraints.append(section.get("body", ""))
        
        if constraints:
            sections.append("## 约束条件")
            sections.extend(constraints)
            sections.append("")

        # 验收标准
        acceptance = []
        for section in task.get("sections", []):
            if "验收" in section.get("heading", ""):
                acceptance.append(section.get("body", ""))
        
        if acceptance:
            sections.append("## 验收标准")
            sections.extend(acceptance)
            sections.append("")

        # 相关文件
        if "files" in task and task["files"]:
            sections.append("## 相关文件")
            for file in task["files"]:
                sections.append(f"- {file}")
            sections.append("")

        # 依赖信息
        if task.get("dependencies"):
            sections.append("## 依赖任务")
            sections.append(f"依赖：{task['dependencies']}")
            sections.append("注意：所有依赖任务已完成，可以开始实现。")
            sections.append("")

        return "\n".join(sections)

    def get_statistics(self) -> dict:
        """获取任务统计信息"""
        document = self.get_document()
        tasks = document.get("tasks", [])
        
        stats = {
            "total": len(tasks),
            "by_status": {},
            "by_type": {},
        }

        for task in tasks:
            status = task.get("status", "PENDING")
            task_type = task.get("type", "unknown")
            
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            stats["by_type"][task_type] = stats["by_type"].get(task_type, 0) + 1

        return stats
