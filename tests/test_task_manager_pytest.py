from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import task_manager  # noqa: E402
from tasks_store import read_tasks_document  # noqa: E402


def write_board(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cmd_update_updates_json_and_markdown(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: 示例任务

**优先级**: P1
**状态**: OPEN

---
""",
    )

    assert task_manager.cmd_update("001", "DONE", str(board)) == 0
    out = capsys.readouterr().out
    assert "OPEN -> DONE" in out

    document = read_tasks_document(board)
    assert document["tasks"][0]["status"] == "DONE"
    assert '"status": "DONE"' in (tmp_path / "planning" / "tasks.json").read_text(encoding="utf-8")
    assert "**状态**: DONE" in board.read_text(encoding="utf-8")


def test_cmd_select_returns_no_executable_tasks_when_blocked(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: 阻塞任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: #999

---
""",
    )

    assert task_manager.cmd_select(False, str(board)) == 0
    assert capsys.readouterr().out.strip() == "NO_EXECUTABLE_TASKS"


def test_cmd_detect_falls_back_without_task_board(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    log_dir = tmp_path / ".dual-ai-collab" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "task-001.exit").write_text("0\n", encoding="utf-8")
    (log_dir / "task-001.pid").write_text("999999\n", encoding="utf-8")

    assert task_manager.cmd_detect("001", "999999", "planning/codex-tasks.md") == 0
    assert "SUCCESS" in capsys.readouterr().out


def test_cmd_summary_reports_generated_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: 示例任务

**状态**: VERIFIED

---
""",
    )

    assert task_manager.cmd_summary(str(board), report=True) == 0
    out = capsys.readouterr().out
    assert "总任务: 1" in out
    assert "报告已写入:" in out
    reports = list((tmp_path / "planning" / "progress-reports").glob("*-progress.md"))
    assert reports
