#!/usr/bin/env python3
"""任务执行历史 - 简化版。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from .store import atomic_write
except ImportError:
    from store import atomic_write


@dataclass
class ExecutionRecord:
    """执行记录"""
    task_id: str
    start_time: str
    end_time: str | None
    duration_seconds: float | None
    status: str  # running, success, failed
    droid: str
    complexity: str
    error_message: str | None
    model: str | None = None
    execution_id: str | None = None
    recorded_at: str | None = None
    details: dict = field(default_factory=dict)


class ExecutionHistory:
    """执行历史管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.history_dir = project_root / ".task-management" / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def record_start(
        self,
        task_id: str,
        droid: str,
        complexity: str,
        model: str | None = None,
        details: dict | None = None,
    ) -> str:
        """记录任务开始，返回执行 ID"""
        self._validate_id(task_id)
        execution_id = f"{task_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:12]}"

        record = ExecutionRecord(
            task_id=task_id,
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=None,
            duration_seconds=None,
            status="running",
            droid=droid,
            complexity=complexity,
            error_message=None,
            model=model,
            execution_id=execution_id,
            details=details or {},
        )

        self._save_record(execution_id, record)
        return execution_id

    def record_completion(
        self,
        execution_id: str,
        status: str,
        error_message: str | None = None,
        *,
        ended_at: str | None = None,
        time_unknown: bool = False,
        details: dict | None = None,
    ) -> None:
        """记录任务完成；details 与状态在同一次写入中保存"""
        record = self._load_record(execution_id)
        if not record:
            raise ValueError("执行记录不存在")
        if record.status != "running":
            if record.status == status:
                return
            raise ValueError("已结束的派发不能覆盖；纠正或重试须新建记录")
        if status not in {"success", "failed", "interrupted"}:
            raise ValueError("无效的派发结果")

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(record.start_time)

        end = datetime.fromisoformat(ended_at) if ended_at else now
        if end.tzinfo is None or not start <= end <= now:
            raise ValueError("结束时间必须带时区且位于开始时间与当前时间之间")
        record.end_time = None if time_unknown else end.isoformat()
        record.duration_seconds = None if time_unknown else (end - start).total_seconds()
        record.recorded_at = now.isoformat()
        record.status = status
        record.error_message = error_message
        if details:
            record.details.update(details)

        self._save_record(execution_id, record)

    def get_task_history(self, task_id: str) -> list[ExecutionRecord]:
        """获取任务的所有执行记录"""
        self._validate_id(task_id)
        records = []
        for file in self.history_dir.glob(f"{task_id}-*.json"):
            record = self._load_record(file.stem)
            if record:
                records.append(record)
        return sorted(records, key=lambda r: r.start_time, reverse=True)

    def get_all_history(self) -> list[ExecutionRecord]:
        """获取所有执行记录"""
        records = []
        for file in self.history_dir.glob("*.json"):
            record = self._load_record(file.stem)
            if record:
                records.append(record)
        return sorted(records, key=lambda r: r.start_time, reverse=True)

    def _save_record(self, execution_id: str, record: ExecutionRecord) -> None:
        """保存记录"""
        self._validate_id(execution_id)
        file_path = self.history_dir / f"{execution_id}.json"
        content = json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n"
        atomic_write(file_path, content)

    def _load_record(self, execution_id: str) -> ExecutionRecord | None:
        """加载记录"""
        self._validate_id(execution_id)
        file_path = self.history_dir / f"{execution_id}.json"
        if not file_path.exists():
            return None

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return ExecutionRecord(**data)
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _validate_id(value: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("无效的任务或执行 ID")
