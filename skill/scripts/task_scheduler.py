#!/usr/bin/env python3
"""智能任务调度器。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tasks_store import CliError, read_tasks_document, find_task, dependency_ids, executable_tasks
from task_history import get_task_statistics


def get_system_resources() -> dict[str, Any]:
    """获取系统资源使用情况。"""
    try:
        import psutil
    except ImportError as exc:
        raise CliError("调度分析需要 psutil，请运行 python3 -m pip install psutil") from exc
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "available_memory_mb": psutil.virtual_memory().available / (1024 * 1024),
        "disk_usage_percent": psutil.disk_usage("/").percent,
    }


def estimate_task_resources(task: dict[str, Any]) -> dict[str, Any]:
    """估算任务所需资源。"""
    execution_level = task.get("execution_level", "normal")

    # 基于执行级别的资源估算
    resource_map = {
        "quick": {"cpu_weight": 1, "memory_mb": 256, "estimated_minutes": 3},
        "normal": {"cpu_weight": 2, "memory_mb": 512, "estimated_minutes": 5},
        "heavy": {"cpu_weight": 4, "memory_mb": 1024, "estimated_minutes": 10},
    }

    base_resources = resource_map.get(execution_level, resource_map["normal"])

    # 从历史数据调整估算
    stats = get_task_statistics(task["id"])
    if stats.get("avg_duration_seconds"):
        estimated_minutes = stats["avg_duration_seconds"] / 60
        base_resources["estimated_minutes"] = estimated_minutes

    return base_resources


def calculate_task_priority(task: dict[str, Any], tasks: dict[str, Any]) -> float:
    """计算任务的优先级分数（越高越优先）。"""
    score = 0.0

    # 1. 基础优先级权重
    priority_weights = {
        "P0": 100,
        "P1": 50,
        "P2": 20,
        "P3": 10,
    }
    priority = task.get("priority", "P2")
    score += priority_weights.get(priority, 10)

    # 2. 依赖深度惩罚（被依赖越多，优先级越高）
    task_num = task["id"]
    dependent_count = sum(
        1 for t in tasks.get("tasks", [])
        if any(find_task(tasks, dep) is task for dep in dependency_ids(t.get("dependencies")))
    )
    score += dependent_count * 20

    # 3. 执行级别加权（快速任务优先）
    level_weights = {
        "quick": 10,
        "normal": 5,
        "heavy": 1,
    }
    execution_level = task.get("execution_level", "normal")
    score += level_weights.get(execution_level, 5)

    # 4. 历史成功率加权
    stats = get_task_statistics(task_num)
    if stats.get("executions", 0) > 0:
        success_rate = stats.get("successes", 0) / stats["executions"]
        # 失败率高的任务优先级降低
        score *= (0.5 + success_rate * 0.5)

    return score


def rank_available_tasks(
    available_tasks: list[dict[str, Any]],
    tasks: dict[str, Any],
    resource_limit: dict[str, Any] | None = None,
    system_resources: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """选择最佳任务执行。

    Args:
        available_tasks: 可执行的任务列表
        tasks: 完整任务文档
        resource_limit: 资源限制（可选）

    Returns:
        按分数排序的可执行任务；无候选时返回空列表
    """
    eligible = {task["id"] for task in executable_tasks(tasks)}
    available_tasks = [task for task in available_tasks if task["id"] in eligible]
    if not available_tasks:
        return []

    # 获取当前系统资源
    system_resources = system_resources if system_resources is not None else get_system_resources()

    # 过滤资源不足的任务
    candidates = []
    for task in available_tasks:
        required = estimate_task_resources(task)

        # 检查资源限制
        if resource_limit:
            if required["memory_mb"] > resource_limit.get("max_memory_mb", float("inf")):
                continue
            if required["cpu_weight"] > resource_limit.get("max_cpu_weight", float("inf")):
                continue

        # 检查系统资源
        if system_resources["memory_percent"] > 90:
            # 内存紧张，只执行轻量任务
            if required["memory_mb"] > 256:
                continue

        if system_resources["cpu_percent"] > 80:
            # CPU 繁忙，只执行轻量任务
            if required["cpu_weight"] > 2:
                continue

        candidates.append(task)

    if not candidates:
        return []

    # 计算优先级并排序
    scored_tasks = [
        (task, calculate_task_priority(task, tasks))
        for task in candidates
    ]
    scored_tasks.sort(key=lambda x: x[1], reverse=True)

    return [task for task, _ in scored_tasks]


def estimate_remaining_time(tasks: dict[str, Any]) -> dict[str, Any]:
    """估算剩余完成时间。"""
    task_list = tasks.get("tasks", [])

    remaining_tasks = [
        t for t in task_list
        if t.get("status") in ("OPEN", "IN_PROGRESS")
    ]

    if not remaining_tasks:
        return {
            "remaining_tasks": 0,
            "estimated_minutes": 0,
            "estimated_hours": 0,
            "with_parallelism_hours": 0,
        }

    total_minutes = 0
    for task in remaining_tasks:
        resources = estimate_task_resources(task)
        total_minutes += resources["estimated_minutes"]

    return {
        "remaining_tasks": len(remaining_tasks),
        "estimated_minutes": total_minutes,
        "estimated_hours": total_minutes / 60,
        "with_parallelism_hours": total_minutes / 60 / 2,  # 假设平均 2 个并行
    }


def generate_schedule_report() -> str:
    """生成调度建议报告。"""
    tasks = read_tasks_document()

    lines = ["# 智能调度分析报告\n"]

    # 系统资源
    resources = get_system_resources()
    lines.append("## 系统资源状态")
    lines.append(f"- CPU 使用率: {resources['cpu_percent']:.1f}%")
    lines.append(f"- 内存使用率: {resources['memory_percent']:.1f}%")
    lines.append(f"- 可用内存: {resources['available_memory_mb']:.0f} MB")
    lines.append(f"- 磁盘使用率: {resources['disk_usage_percent']:.1f}%\n")

    # 剩余时间估算
    remaining = estimate_remaining_time(tasks)
    lines.append("## 完成时间估算")
    lines.append(f"- 剩余任务: {remaining['remaining_tasks']} 个")
    lines.append(f"- 串行执行预计: {remaining['estimated_hours']:.1f} 小时")
    lines.append(f"- 理想双 worker 估算（未计依赖等待）: {remaining['with_parallelism_hours']:.1f} 小时\n")

    # 任务优先级排序
    task_list = tasks.get("tasks", [])
    open_tasks = executable_tasks(tasks)

    open_tasks = rank_available_tasks(open_tasks, tasks, system_resources=resources)
    if not open_tasks:
        lines.append("暂无满足依赖与资源条件的可执行任务。")
    if open_tasks:
        lines.append("## 推荐执行顺序（前 5 个）")

        scored = [
            (task, calculate_task_priority(task, tasks))
            for task in open_tasks
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        for i, (task, score) in enumerate(scored[:5], 1):
            task_num = task["id"]
            title = task.get("title", "")
            priority = task.get("priority", "P2")
            level = task.get("execution_level", "normal")

            lines.append(f"{i}. 任务 #{task_num}: {title}")
            lines.append(f"   - 优先级: {priority}, 执行级别: {level}")
            lines.append(f"   - 调度分数: {score:.1f}")

            resources = estimate_task_resources(task)
            lines.append(f"   - 预计耗时: {resources['estimated_minutes']:.1f} 分钟\n")

    return "\n".join(lines)


def load_balance_tasks(
    tasks: dict[str, Any],
    worker_count: int = 2,
) -> list[list[str]]:
    """负载均衡分配任务到多个 worker。

    Args:
        tasks: 任务文档
        worker_count: worker 数量

    Returns:
        每个 worker 的任务列表
    """
    if worker_count < 1:
        raise CliError("worker_count 必须大于 0")
    task_list = tasks.get("tasks", [])
    open_tasks = executable_tasks(tasks)

    # 按优先级和资源需求排序
    scored = [
        (task, calculate_task_priority(task, tasks), estimate_task_resources(task))
        for task in open_tasks
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # 初始化 worker 负载
    workers = [{"tasks": [], "load_minutes": 0.0} for _ in range(worker_count)]

    # 贪心分配：每次分配给负载最小的 worker
    for task, _, resources in scored:
        min_worker = min(workers, key=lambda w: w["load_minutes"])
        min_worker["tasks"].append(task["id"])
        min_worker["load_minutes"] += resources["estimated_minutes"]

    return [w["tasks"] for w in workers]


def select_best_task(available_tasks, tasks, resource_limit=None):
    ranked = rank_available_tasks(available_tasks, tasks, resource_limit)
    return ranked[0] if ranked else None
