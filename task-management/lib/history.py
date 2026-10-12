#!/usr/bin/env python3
"""任务执行历史 - 简化版。"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    ) -> str:
        """记录任务开始，返回执行 ID"""
        execution_id = f"{task_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
        record = ExecutionRecord(
            task_id=task_id,
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=None,
            duration_seconds=None,
            status="running",
            droid=droid,
            complexity=complexity,
            error_message=None,
        )
        
        self._save_record(execution_id, record)
        return execution_id

    def record_completion(
        self,
        execution_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """记录任务完成"""
        record = self._load_record(execution_id)
        if not record:
            return

        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(record.start_time)
        
        record.end_time = now.isoformat()
        record.duration_seconds = (now - start).total_seconds()
        record.status = status
        record.error_message = error_message
        
        self._save_record(execution_id, record)

    def get_task_history(self, task_id: str) -> list[ExecutionRecord]:
        """获取任务的所有执行记录"""
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
        file_path = self.history_dir / f"{execution_id}.json"
        content = json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n"
        atomic_write(file_path, content)

    def _load_record(self, execution_id: str) -> ExecutionRecord | None:
        """加载记录"""
        file_path = self.history_dir / f"{execution_id}.json"
        if not file_path.exists():
            return None
        
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return ExecutionRecord(**data)
        except (OSError, json.JSONDecodeError, TypeError):
            return None
