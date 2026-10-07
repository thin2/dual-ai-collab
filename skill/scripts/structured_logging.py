#!/usr/bin/env python3
"""结构化日志工具 - 统一的事件、指标和跟踪日志。"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any


def _write_log_entry(entry: dict[str, Any]) -> None:
    """写入一条结构化日志条目到 stderr。"""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        print(json.dumps(entry, ensure_ascii=False), file=sys.stderr, flush=True)
    except OSError:
        pass  # 静默失败，不影响主流程


def log_event(event_name: str, level: str = "INFO", **attributes) -> None:
    """记录一个事件。

    Args:
        event_name: 事件名称（如 "task_started", "adapter_fallback"）
        level: 日志级别（INFO, WARN, ERROR）
        **attributes: 事件属性（任意键值对）
    """
    entry = {"event": event_name, "level": level, **attributes}
    _write_log_entry(entry)


def log_metric(metric_name: str, value: float, unit: str = "", **tags) -> None:
    """记录一个指标。

    Args:
        metric_name: 指标名称（如 "execution_duration", "prompt_size"）
        value: 指标值
        unit: 单位（如 "seconds", "bytes"）
        **tags: 指标标签（任意键值对）
    """
    entry = {
        "type": "metric",
        "metric": metric_name,
        "value": value,
        "unit": unit,
        "tags": tags,
    }
    _write_log_entry(entry)


def log_span_start(span_name: str, **attributes) -> dict[str, Any]:
    """开始一个跨度（用于追踪操作的开始和结束）。

    Args:
        span_name: 跨度名称（如 "task_execution", "adapter_routing"）
        **attributes: 跨度属性

    Returns:
        跨度上下文（传给 log_span_end）
    """
    span_id = f"{span_name}_{int(time.time() * 1000000)}"
    start_time = time.time()

    entry = {
        "event": f"{span_name}.started",
        **attributes,
    }
    _write_log_entry(entry)

    return {
        "span_id": span_id,
        "span_name": span_name,
        "start_time": start_time,
        "attributes": attributes,
    }


def log_span_end(span_context: dict[str, Any], success: bool = True, **attributes) -> None:
    """结束一个跨度。

    Args:
        span_context: log_span_start 返回的上下文
        success: 操作是否成功
        **attributes: 额外的结束时属性
    """
    end_time = time.time()
    duration = end_time - span_context["start_time"]

    # 输出 span.completed 事件
    entry = {
        "event": f"{span_context['span_name']}.completed",
        "success": success,
        "duration_seconds": duration,
        **span_context["attributes"],
        **attributes,
    }
    _write_log_entry(entry)

    # 输出 duration 指标
    metric_entry = {
        "type": "metric",
        "metric": f"{span_context['span_name']}_duration",
        "value": duration,
        "unit": "seconds",
        "tags": {},
    }
    _write_log_entry(metric_entry)
