from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from tasks_store import (  # noqa: E402
    CliError,
    extract_acceptance_commands,
    find_task,
    read_tasks_document,
    render_markdown,
    write_tasks_document,
)


def test_markdown_import_creates_json_store(tmp_path):
    planning = tmp_path / "planning"
    planning.mkdir()
    markdown = planning / "codex-tasks.md"
    markdown.write_text(
        """# 测试任务板

## 任务 #001: 任务一

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无

### 任务描述
实现功能

### 验收标准
- [ ] `python -c "print(1)"` 通过
- [ ] `python -c "print(2)"` 通过

---
""",
        encoding="utf-8",
    )

    document = read_tasks_document(markdown)

    assert (planning / "tasks.json").exists()
    assert document["tasks"][0]["status"] == "OPEN"
    assert document["tasks"][0]["acceptance_commands"] == ['python -c "print(1)"', 'python -c "print(2)"']


def test_write_tasks_document_updates_markdown_view(tmp_path):
    planning = tmp_path / "planning"
    planning.mkdir()
    markdown = planning / "codex-tasks.md"
    markdown.write_text(
        """## 任务 #001: 任务一

**优先级**: P1
**状态**: OPEN

### 任务描述
描述

---
""",
        encoding="utf-8",
    )

    document = read_tasks_document(markdown)
    task = find_task(document, "001")
    assert task is not None
    task["status"] = "DONE"
    write_tasks_document(document, markdown)

    content = markdown.read_text(encoding="utf-8")
    assert "**状态**: DONE" in content
    assert '"status": "DONE"' in (planning / "tasks.json").read_text(encoding="utf-8")


def test_render_markdown_preserves_extra_fields():
    document = {
        "version": 1,
        "header": "# Header",
        "tasks": [
            {
                "id": "001",
                "title": "任务一",
                "priority": "P1",
                "status": "OPEN",
                "status_explicit": True,
                "assigned_to": "",
                "dependencies": "无",
                "execution_level": "",
                "stall_threshold_minutes": "",
                "field_order": ["priority", "status", "extra:创建时间"],
                "extra_fields": {"创建时间": "2026-04-14"},
                "sections": [{"heading": "任务描述", "body": "描述"}],
            }
        ],
    }

    markdown = render_markdown(document)
    assert "**创建时间**: 2026-04-14" in markdown
    assert "### 任务描述" in markdown


def test_extract_acceptance_commands_returns_all_backtick_commands():
    task = {
        "sections": [
            {
                "heading": "验收标准",
                "body": '- [ ] `python -c "print(1)"` 和 `python -c "print(2)"`',
            }
        ]
    }
    assert extract_acceptance_commands(task) == ['python -c "print(1)"', 'python -c "print(2)"']


def test_read_tasks_document_raises_when_missing(tmp_path):
    missing = tmp_path / "planning" / "codex-tasks.md"
    try:
        read_tasks_document(missing)
    except CliError as exc:
        assert "任务板不存在" in str(exc)
    else:
        raise AssertionError("expected CliError")
