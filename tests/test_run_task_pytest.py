from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import run_task  # noqa: E402
from run_store import read_run_record, write_run_record  # noqa: E402
from tasks_store import CliError  # noqa: E402


TASK_BOARD = """# Codex 任务板 - demo

## 任务 #001: 有模型和执行级别

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无
**执行级别**: heavy
**模型**: gpt-test

---

## 任务 #002: 显式推理强度

**优先级**: P2
**状态**: OPEN
**依赖任务**: 无
**执行级别**: heavy
**推理强度**: minimal

---
"""

STUB_CODEX = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
stdin = sys.stdin.read()
print("ARGS " + json.dumps(args))
print("STDIN_LEN %d" % len(stdin))
sys.stdout.flush()
if "-o" in args:
    with open(args[args.index("-o") + 1], "w") as fh:
        json.dump({"result": "DONE", "summary": "ok", "files_changed": [], "acceptance": [],
                   "verification": [], "notes": []}, fh)
sys.exit(0)
"""


def _write_board(tmp_path: Path) -> None:
    (tmp_path / "planning").mkdir()
    (tmp_path / "planning" / "codex-tasks.md").write_text(TASK_BOARD, encoding="utf-8")


def test_build_codex_command_defaults_use_sandbox_and_stdin():
    cmd = run_task.build_codex_command("/repo")
    assert cmd == ["codex", "exec", "-C", "/repo", "-s", "workspace-write", "-"]
    assert "--full-auto" not in cmd


def test_build_codex_command_includes_all_options():
    cmd = run_task.build_codex_command(
        "/repo", model="m1", effort="high", sandbox="read-only", schema_file="s.json", result_file="r.json"
    )
    assert cmd[-1] == "-"
    assert cmd[cmd.index("-m") + 1] == "m1"
    assert cmd[cmd.index("-c") + 1] == "model_reasoning_effort=high"
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert cmd[cmd.index("--output-schema") + 1] == "s.json"
    assert cmd[cmd.index("-o") + 1] == "r.json"


def test_resolve_exec_options_reads_task_board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_board(tmp_path)
    assert run_task.resolve_exec_options("001", None, None) == {"model": "gpt-test", "effort": "high"}
    # 显式 **推理强度** 优先于执行级别推导
    assert run_task.resolve_exec_options("002", None, None) == {"model": None, "effort": "minimal"}
    # 命令行参数优先于任务板
    assert run_task.resolve_exec_options("001", "cli-model", "low") == {"model": "cli-model", "effort": "low"}


def test_resolve_exec_options_without_task_board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_task.resolve_exec_options("001", None, None) == {"model": None, "effort": None}


def test_resolve_exec_options_rejects_unknown_effort(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CliError):
        run_task.resolve_exec_options("001", None, "turbo")


def test_load_prompt_validation(tmp_path):
    prompt_file = tmp_path / "p.md"
    prompt_file.write_text("from file", encoding="utf-8")
    assert run_task._load_prompt(None, str(prompt_file)) == "from file"
    assert run_task._load_prompt("inline", None) == "inline"
    with pytest.raises(CliError):
        run_task._load_prompt("inline", str(prompt_file))
    with pytest.raises(CliError):
        run_task._load_prompt(None, None)


def test_archive_previous_run_moves_log_and_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs = Path(".dual-ai-collab/logs")
    logs.mkdir(parents=True)
    (logs / "task-001.log").write_text("old log", encoding="utf-8")
    (logs / "task-001.result.json").write_text("{}", encoding="utf-8")
    write_run_record(
        {
            "run_id": "task-001-old",
            "task_num": "001",
            "pid": 0,
            "status": "failed",
            "log_file": str(logs / "task-001.log"),
            "result_file": str(logs / "task-001.result.json"),
        }
    )

    run_task._archive_previous_run("001")

    assert not (logs / "task-001.log").exists()
    assert (logs / "history" / "task-001-old.log").read_text(encoding="utf-8") == "old log"
    assert (logs / "history" / "task-001-old.result.json").exists()


def test_archive_previous_run_refuses_while_running(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".dual-ai-collab/logs").mkdir(parents=True)
    write_run_record({"run_id": "r", "task_num": "001", "pid": os.getpid(), "status": "running"})
    with pytest.raises(CliError):
        run_task._archive_previous_run("001")


@pytest.mark.skipif(os.name == "nt", reason="stub codex 使用 shebang 脚本")
def test_start_end_to_end_with_stub_codex(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_board(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "codex"
    stub.write_text(STUB_CODEX, encoding="utf-8")
    stub.chmod(0o755)

    # 环境变量会传递到子进程
    monkeypatch.setenv("CODEX_BIN", str(stub))

    long_prompt = "x" * 50000
    run_task.cmd_start("001", long_prompt, "direct", str(tmp_path))

    record = read_run_record("001")
    assert record["model"] == "gpt-test"
    assert record["effort"] == "high"
    assert record["sandbox"] == "workspace-write"

    deadline = time.time() + 15
    status = {}
    while time.time() < deadline:
        record = read_run_record("001")
        status = run_task._status_direct(record)
        if status["status"] != "running":
            break
        time.sleep(0.2)

    assert status["status"] == "success"
    assert status["result"]["result"] == "DONE"
    log = Path(record["log_file"]).read_text(encoding="utf-8")
    args = json.loads(log.split("ARGS ", 1)[1].splitlines()[0])
    assert args[-1] == "-"
    assert "--output-schema" in args
    assert f"STDIN_LEN {len(long_prompt)}" in log


def test_resolve_exec_options_supports_legacy_model_field(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "planning").mkdir()
    (tmp_path / "planning/tasks.json").write_text(json.dumps({"tasks": [{
        "id": "001", "status": "OPEN", "extra_fields": {"模型": "legacy-model"}
    }]}), encoding="utf-8")
    assert run_task.resolve_exec_options("001", None, None)["model"] == "legacy-model"
