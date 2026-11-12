#!/usr/bin/env python3
"""任务板核心逻辑 - 简化版，专注于任务管理。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from .store import (
        DEFAULT_TASKS_MD,
        READY_STATUSES,
        ManagedTaskError,
        _normalize_task,
        _normalize_task_num,
        extract_acceptance_commands,
        find_task,
        open_tasks_sorted,
        read_tasks_document,
        select_parallel_batch,
        update_tasks_document,
        write_tasks_document,
    )
except ImportError:
    from store import (
        DEFAULT_TASKS_MD,
        READY_STATUSES,
        ManagedTaskError,
        _normalize_task,
        _normalize_task_num,
        extract_acceptance_commands,
        find_task,
        open_tasks_sorted,
        read_tasks_document,
        select_parallel_batch,
        update_tasks_document,
        write_tasks_document,
    )


WORKFLOW_FIELDS = ("status", "execution_id", "failed_attempts", "last_failure")


class TaskBoard:
    """任务板管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.task_file = project_root / DEFAULT_TASKS_MD

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

    def add_tasks(self, tasks: list[dict], replace: bool = False) -> list[str]:
        """在文件锁内追加任务；replace 为真时可以改写待开始的同号任务，返工记录保留。全部合格才写入。"""
        def mutate(document: dict) -> list[str]:
            board = document.setdefault("tasks", [])
            positions = {_normalize_task_num(str(task.get("id", ""))): index for index, task in enumerate(board)}
            added = []
            for task in tasks:
                if not isinstance(task, dict):
                    raise ValueError("每个任务必须是 JSON 对象")
                task_id = task.get("id")
                if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
                    raise ValueError(f"任务编号必须是字符串，只含字母、数字、下划线和连字符: {task_id!r}")
                if not isinstance(task.get("title"), str) or not task["title"].strip():
                    raise ValueError(f"任务 {task_id} 缺少 title")
                if task.get("status", "PENDING") not in READY_STATUSES:
                    raise ValueError(f"任务 {task_id}: 新任务的状态只能是 PENDING，其余状态由执行流程写入")
                if task.get("execution_id") or task.get("integration"):
                    raise ValueError(f"任务 {task_id}: execution_id 和 integration 由执行流程写入，不能手工填写")
                task = _normalize_task({"status": "PENDING", **task})
                key = _normalize_task_num(task_id)
                if key not in positions:
                    positions[key] = len(board)
                    board.append(task)
                elif not replace:
                    raise ValueError(f"任务编号 {task_id} 已存在；修改还没开始的任务用 --replace")
                else:
                    current = board[positions[key]]
                    if current.get("status", "PENDING") not in READY_STATUSES:
                        raise ValueError(f"任务 {task_id} 正在进行或已经完成，不能改写；"
                                         "要改规划先 execution finish，再用 execution retry 说明续做范围")
                    # The rework trail belongs to the workflow, not to the plan being rewritten.
                    task.update({field: current[field] for field in WORKFLOW_FIELDS if field in current})
                    board[positions[key]] = task
                added.append(task_id)
            return added

        return update_tasks_document(self.task_file, mutate)

    def _update(self, task_id: str, change, require_unmanaged: bool = False) -> dict:
        """在任务板文件锁内修改单个任务，返回修改后的任务"""
        def mutate(document: dict) -> dict:
            task = find_task(document, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            if require_unmanaged and task.get("execution_id"):
                raise ManagedTaskError(
                    "受管任务请使用 execution finish/accept/retry/block/unblock 或 integrate 更新状态；"
                    "先 execution inspect，不自动丢弃部分成果"
                )
            change(task)
            return task

        return update_tasks_document(self.task_file, mutate)

    def update_task(self, task_id: str, changes: dict, require_unmanaged: bool = False) -> dict:
        """修改任务的若干字段；require_unmanaged 为真时拒绝修改受管任务"""
        return self._update(task_id, lambda task: task.update(changes), require_unmanaged)

    def update_task_status(self, task_id: str, status: str, reset_retries: bool = False,
                           require_unmanaged: bool = False) -> None:
        """更新任务状态"""
        changes = {"status": status}
        if reset_retries:
            changes["failed_attempts"] = 0
        self.update_task(task_id, changes, require_unmanaged)

    def record_failure(self, task_id: str, max_retries: int, block: bool = False, reason: str = "",
                       require_unmanaged: bool = False) -> tuple[int, str]:
        """记录一次失败：未超过重试上限时回到 PENDING，否则改为 BLOCKED。返回 (失败次数, 新状态)"""
        def change(task: dict) -> None:
            failures = int(task.get("failed_attempts", 0)) + 1
            task["failed_attempts"] = failures
            task["last_failure"] = reason
            task["status"] = "BLOCKED" if block or failures > max_retries else "PENDING"

        task = self._update(task_id, change, require_unmanaged)
        return task["failed_attempts"], task["status"]

    def confirm_integration(self, task_id: str, commit: str, target_repo: str, note: str = "") -> dict:
        """记录集成确认并标记 DONE；依赖它的任务从此解锁"""
        def change(task: dict) -> None:
            task["integration"] = {
                "target_repo": target_repo,
                "commit": commit,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": note,
            }
            task["status"] = "DONE"

        return self._update(task_id, change)

    def get_next_task(self, roles: dict | None = None) -> dict | None:
        """下一个可以开始的任务，即 select_batch 的第一项；已开始或停下等人处理的任务不算"""
        batch = self.select_batch(roles, max_parallel=1)["batch"]
        return batch[0] if batch else None

    def select_batch(self, roles: dict | None = None, max_parallel: int = 2) -> dict:
        """挑出下一批可以并行执行的任务，见 store.select_parallel_batch"""
        return select_parallel_batch(self.get_document(), roles, max_parallel)

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
        """构建执行上下文：派发时交给子 Agent，直接执行时给当前会话看"""
        sections = [f"# 任务 {task['id']}: {task.get('title', '未命名任务')}", ""]

        if task.get("description"):
            sections.extend(["## 任务描述", task["description"], ""])
        if task.get("last_failure"):
            sections.extend(["## 上次失败与续做要求", task["last_failure"],
                             "先检查已有修改，在现有成果上续做；不要覆盖或清除用户改动。", ""])
        if task.get("acceptance"):
            sections.append("## 必须逐项验证的验收条件")
            for check in task["acceptance"]:
                sections.append(f"- {check['id']}: {check.get('scenario', '')} → {check.get('expected', '')}")
            sections.append("")

        for section in task.get("sections", []):
            heading = section.get("heading", "")
            body = section.get("body", "").strip()
            if heading and body:
                sections.extend([f"## {heading}", body, ""])

        if task.get("files"):
            sections.append("## 允许修改的文件")
            sections.extend(f"- {file}" for file in task["files"])
            sections.append("只修改上面列出的文件；需要改动其他文件时，停止并报告。")
            sections.append("")

        if task.get("dependencies") and task.get("dependencies") != "无":
            sections.extend(["## 依赖任务", f"依赖：{task['dependencies']}", "所有依赖任务已完成，可以开始实现。", ""])

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
