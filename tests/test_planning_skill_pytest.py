#!/usr/bin/env python3
"""planning-collab skill 单元测试。

所有测试通过子进程调用 planning-skill/scripts/，
避免与 skill/scripts/ 中的同名模块冲突。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLANNING_SCRIPTS = ROOT / "planning-skill" / "scripts"
CLI_PY = str(PLANNING_SCRIPTS / "cli.py")
PYTHON = sys.executable


def _run_planning(*args, cwd=None, input_text=None):
    return subprocess.run(
        [PYTHON, CLI_PY, *args],
        capture_output=True, text=True, timeout=10,
        cwd=cwd, input=input_text,
    )


def _run_script(script_name: str, code: str, cwd=None):
    """在 planning-skill/scripts 目录下运行一段 Python 代码。"""
    full_code = f"import sys; sys.path.insert(0, {str(PLANNING_SCRIPTS)!r})\n{code}"
    return subprocess.run(
        [PYTHON, "-c", full_code],
        capture_output=True, text=True, timeout=10,
        cwd=cwd,
    )


SAMPLE_TASKS_MD = textwrap.dedent("""\
    # 任务板

    ## 任务 #001: 第一个任务

    **优先级**: P1
    **状态**: OPEN
    **依赖任务**: 无

    ### 任务描述
    测试任务

    ### 验收标准
    - [ ] `echo ok`

    ---

    ## 任务 #002: 第二个任务

    **优先级**: P2
    **状态**: OPEN
    **依赖任务**: #001

    ### 任务描述
    依赖第一个

    ### 验收标准
    - [ ] `echo ok2`

    ---
""")


@pytest.fixture()
def tmp_project(tmp_path):
    return tmp_path


def _write_sample_tasks(tmp_path: Path) -> Path:
    planning = tmp_path / "planning"
    planning.mkdir(parents=True, exist_ok=True)
    md_path = planning / "codex-tasks.md"
    md_path.write_text(SAMPLE_TASKS_MD, encoding="utf-8")
    return md_path


class TestPlanningInit:
    def test_creates_correct_dirs(self, tmp_project):
        result = _run_planning("init", cwd=str(tmp_project))
        assert result.returncode == 0
        assert "ENV_READY" in result.stdout
        assert (tmp_project / "planning" / "specs").is_dir()
        assert (tmp_project / ".planning-collab" / "checkpoints").is_dir()
        assert not (tmp_project / ".dual-ai-collab").exists()

    def test_no_audit_or_log_dirs(self, tmp_project):
        _run_planning("init", cwd=str(tmp_project))
        assert not (tmp_project / "planning" / "audit-reports").exists()
        assert not (tmp_project / "planning" / "progress-reports").exists()


class TestPlanningCheckpoint:
    def test_rejects_execution_phases(self, tmp_project):
        _run_planning("init", cwd=str(tmp_project))
        for phase in ("developing", "auditing", "fixing"):
            result = _run_planning("checkpoint-write", phase, cwd=str(tmp_project))
            assert result.returncode != 0
            assert "无效的 phase" in result.stderr

    def test_accepts_planning_phases(self, tmp_project):
        _run_planning("init", cwd=str(tmp_project))
        for phase in ("interview", "spec_generated", "tasks_created", "user_approved"):
            result = _run_planning("checkpoint-write", phase, cwd=str(tmp_project))
            assert result.returncode == 0
            assert f"phase={phase}" in result.stdout

    def test_rejects_execution_fields(self, tmp_project):
        _run_planning("init", cwd=str(tmp_project))
        result = _run_planning("checkpoint-write", "interview", "fix_round=2", cwd=str(tmp_project))
        assert result.returncode == 0
        assert "WARNING" in result.stderr
        # Verify fix_round not in checkpoint
        check = _run_planning("checkpoint-check", cwd=str(tmp_project))
        assert "fix_round" not in check.stdout

    def test_accepts_planning_fields(self, tmp_project):
        _run_planning("init", cwd=str(tmp_project))
        result = _run_planning(
            "checkpoint-write", "tasks_created",
            "spec_file=planning/specs/test.md", "task_file=planning/codex-tasks.md", "total_tasks=5",
            cwd=str(tmp_project),
        )
        assert result.returncode == 0
        check = _run_planning("checkpoint-check", cwd=str(tmp_project))
        assert "spec_file" in check.stdout
        assert "total_tasks" in check.stdout


class TestPlanningSelectAndUpdate:
    def test_select_picks_first_open(self, tmp_project):
        _write_sample_tasks(tmp_project)
        result = _run_planning("select", "planning/codex-tasks.md", cwd=str(tmp_project))
        assert result.returncode == 0
        assert result.stdout.strip().startswith("1|001|")

    def test_update_changes_status(self, tmp_project):
        _write_sample_tasks(tmp_project)
        result = _run_planning("update", "001", "IN_PROGRESS", "planning/codex-tasks.md", cwd=str(tmp_project))
        assert result.returncode == 0
        assert "OPEN -> IN_PROGRESS" in result.stdout

    def test_summary(self, tmp_project):
        _write_sample_tasks(tmp_project)
        result = _run_planning("summary", "planning/codex-tasks.md", cwd=str(tmp_project))
        assert result.returncode == 0
        assert "总任务: 2" in result.stdout
        assert "OPEN: 2" in result.stdout


class TestPlanningCli:
    def test_no_run_command(self):
        result = _run_planning("run", "start", "001", "test")
        assert result.returncode == 2

    def test_no_verify_command(self):
        result = _run_planning("verify", "run", "001")
        assert result.returncode == 2

    def test_no_detect_command(self):
        result = _run_planning("detect", "001", "123")
        assert result.returncode == 2