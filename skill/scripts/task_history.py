#!/usr/bin/env python3
"""任务执行历史追踪和分析。"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from uuid import uuid4

from tasks_store import CliError, atomic_write, find_task, read_tasks_document
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_DIR = Path(".dual-ai-collab/history")


@dataclass
class TaskExecution:
    """单次任务执行记录。"""
    task_num: str
    start_time: str
    end_time: str | None
    duration_seconds: float | None
    status: str  # running, success, failed, stopped
    adapter: str | None
    model: str | None
    execution_level: str
    exit_code: int | None
    error_message: str | None
    prompt_size: int | None


def record_task_start(
    task_num: str,
    adapter: str | None = None,
    model: str | None = None,
    execution_level: str = "normal",
    prompt_size: int | None = None,
) -> str:
    """记录任务开始，返回执行ID。"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    execution_id = f"{task_num}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}-{uuid4().hex[:8]}"
    execution = TaskExecution(
        task_num=task_num,
        start_time=datetime.now(timezone.utc).isoformat(),
        end_time=None,
        duration_seconds=None,
        status="running",
        adapter=adapter,
        model=model,
        execution_level=execution_level,
        exit_code=None,
        error_message=None,
        prompt_size=prompt_size,
    )

    history_file = HISTORY_DIR / f"{execution_id}.json"
    atomic_write(history_file, json.dumps(asdict(execution), ensure_ascii=False, indent=2) + "\n")

    return execution_id


def record_task_end(
    execution_id: str,
    status: str,
    exit_code: int | None = None,
    error_message: str | None = None,
    *, blocked_reason: str | None = None, blocked_category: str | None = None,
) -> None:
    """记录任务结束。"""
    history_file = HISTORY_DIR / f"{execution_id}.json"
    if not history_file.exists():
        return

    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    end_time = datetime.now(timezone.utc)
    start_time = datetime.fromisoformat(data["start_time"])
    duration = (end_time - start_time).total_seconds()

    data["end_time"] = end_time.isoformat()
    data["duration_seconds"] = duration
    data["status"] = status
    data["exit_code"] = exit_code
    data["error_message"] = error_message
    data["blocked_reason"] = blocked_reason
    data["blocked_category"] = blocked_category

    atomic_write(history_file, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def get_task_history(task_num: str) -> list[dict[str, Any]]:
    """获取任务的所有执行历史。"""
    if not HISTORY_DIR.exists():
        return []

    history = []
    for file in sorted(HISTORY_DIR.glob(f"{task_num}-*.json"), reverse=True):
        with open(file, "r", encoding="utf-8") as f:
            history.append(json.load(f))

    return history


def get_task_statistics(task_num: str) -> dict[str, Any]:
    """获取任务的统计信息。"""
    history = get_task_history(task_num)
    if not history:
        return {"executions": 0}

    completed = [h for h in history if h["status"] in ("success", "failed")]
    durations = [h["duration_seconds"] for h in completed if h["duration_seconds"]]

    from collections import Counter
    blocked = [h for h in history if h['status'] == 'blocked']
    return {
        "blocked": len(blocked),
        "blocked_categories": dict(Counter(h.get('blocked_category') or 'unknown' for h in blocked)),
        "executions": len(history),
        "successes": len([h for h in history if h["status"] == "success"]),
        "failures": len([h for h in history if h["status"] == "failed"]),
        "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
        "min_duration_seconds": min(durations) if durations else None,
        "max_duration_seconds": max(durations) if durations else None,
        "last_execution": history[0] if history else None,
    }


def get_all_statistics() -> dict[str, Any]:
    """获取所有任务的统计信息。"""
    if not HISTORY_DIR.exists():
        return {"total_executions": 0, "tasks": {}}

    tasks_stats = {}
    total_executions = 0

    for file in HISTORY_DIR.glob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)

        task_num = data["task_num"]
        if task_num not in tasks_stats:
            tasks_stats[task_num] = get_task_statistics(task_num)

        total_executions += 1

    return {
        "total_executions": total_executions,
        "tasks": tasks_stats,
    }


def generate_report() -> str:
    """生成执行历史报告。"""
    stats = get_all_statistics()

    if stats["total_executions"] == 0:
        return "暂无任务执行历史。"

    lines = ["# 任务执行历史报告\n"]
    lines.append(f"**总执行次数**: {stats['total_executions']}\n")
    lines.append(f"**任务数量**: {len(stats['tasks'])}\n\n")

    for task_num, task_stats in sorted(stats["tasks"].items()):
        lines.append(f"## 任务 #{task_num}\n")
        lines.append(f"- 执行次数: {task_stats['executions']}")
        lines.append(f"- 成功: {task_stats['successes']}, 失败: {task_stats['failures']}")

        lines.append(f"- 阻塞: {task_stats['blocked']}，分类: {json.dumps(task_stats['blocked_categories'], ensure_ascii=False)}")
        if task_stats['last_execution'].get('blocked_reason'):
            lines.append(f"- 最近阻塞原因: {task_stats['last_execution']['blocked_reason']}")

        if task_stats["avg_duration_seconds"]:
            avg = task_stats["avg_duration_seconds"]
            lines.append(f"- 平均耗时: {avg:.1f}秒 ({avg/60:.1f}分钟)")
            lines.append(f"- 最快: {task_stats['min_duration_seconds']:.1f}秒")
            lines.append(f"- 最慢: {task_stats['max_duration_seconds']:.1f}秒")

        if task_stats["last_execution"]:
            last = task_stats["last_execution"]
            lines.append(f"- 最后执行: {last['start_time']}")
            lines.append(f"- 最后状态: {last['status']}")
            if last.get("adapter"):
                lines.append(f"- 使用适配器: {last['adapter']}")

        lines.append("")

    return "\n".join(lines)


@contextmanager
def track_execution(task_num: str, *, adapter: str, model: str | None, prompt_file: str):
    """Record worker outcomes; execution success does not imply acceptance passed."""
    try:
        task = find_task(read_tasks_document(), task_num) or {}
    except CliError:
        task = {}
    prompt_path = Path(prompt_file)
    execution_id = record_task_start(
        task_num, adapter=adapter, model=model,
        execution_level=task.get("execution_level") or "normal",
        prompt_size=prompt_path.stat().st_size if prompt_path.exists() else None,
    )
    try:
        yield execution_id
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        status = "success" if code == 0 else "stopped" if code == 143 else "failed"
        record_task_end(execution_id, status, code, None if code == 0 else f"Worker exited with code {code}")
        raise
    except BaseException as exc:
        record_task_end(execution_id, "failed", 1, f"{type(exc).__name__}: {exc}")
        raise
    else:
        record_task_end(execution_id, "success", 0)
