from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from structured_logging import log_event, log_metric, log_span_start, log_span_end  # noqa: E402


def test_log_event_outputs_json(capsys):
    log_event("test_event", level="INFO", key1="value1", key2=42)
    captured = capsys.readouterr()

    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1

    event = json.loads(lines[0])
    assert event["event"] == "test_event"
    assert event["level"] == "INFO"
    assert event["key1"] == "value1"
    assert event["key2"] == 42
    assert "timestamp" in event


def test_log_metric_outputs_json(capsys):
    log_metric("test_metric", 123.45, unit="ms", tag1="val1")
    captured = capsys.readouterr()

    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1

    metric = json.loads(lines[0])
    assert metric["type"] == "metric"
    assert metric["metric"] == "test_metric"
    assert metric["value"] == 123.45
    assert metric["unit"] == "ms"
    assert metric["tags"]["tag1"] == "val1"


def test_log_span_measures_duration(capsys):
    import time

    ctx = log_span_start("test_span", op="test")
    time.sleep(0.1)
    log_span_end(ctx, success=True, result="ok")

    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]

    # Should have: span.started event, span.completed event, span_duration metric
    assert len(lines) == 3

    started = json.loads(lines[0])
    assert started["event"] == "test_span.started"
    assert started["op"] == "test"

    completed = json.loads(lines[1])
    assert completed["event"] == "test_span.completed"
    assert completed["success"] is True
    assert completed["result"] == "ok"
    assert completed["duration_seconds"] >= 0.1

    metric = json.loads(lines[2])
    assert metric["metric"] == "test_span_duration"
    assert metric["value"] >= 0.1
