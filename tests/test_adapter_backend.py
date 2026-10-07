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
from run_store import read_run_record  # noqa: E402
from tasks_store import CliError  # noqa: E402


TASK_BOARD = """# Codex 任务板 - adapter test

## 任务 #101: 快速任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无
**执行级别**: quick

---

## 任务 #102: 普通任务

**优先级**: P2
**状态**: OPEN
**依赖任务**: 无
**执行级别**: normal

---

## 任务 #103: 复杂任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无
**执行级别**: heavy

---
"""

# 模拟适配器 - 类似 codex 的接口
STUB_ADAPTER = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
stdin = sys.stdin.read()
print("ADAPTER_ARGS " + json.dumps(args))
print("ADAPTER_STDIN_LEN %d" % len(stdin))
sys.stdout.flush()
if "-o" in args:
    with open(args[args.index("-o") + 1], "w") as fh:
        json.dump({"result": "DONE", "summary": "adapter ok", "files_changed": [],
                   "acceptance": [], "verification": [], "notes": []}, fh)
sys.exit(0)
"""

# 配置文件 - 使用与默认配置兼容的适配器名称
CONFIG_JSON = {
    "default_backend": "adapter",
    "default_sandbox": "workspace-write",
    "adapter_commands": {
        "deepseek-cli": ["test-adapter-quick", "exec", "-"],
        "claude-cli": ["test-adapter-normal", "exec", "-"],
        "codex": ["test-adapter-heavy", "exec", "-"]
    },
    "adapter_fallback_order": ["deepseek-cli", "claude-cli", "codex"]
}


def _write_board(tmp_path: Path) -> None:
    (tmp_path / "planning").mkdir()
    (tmp_path / "planning" / "codex-tasks.md").write_text(TASK_BOARD, encoding="utf-8")


def _write_config(tmp_path: Path) -> None:
    config_dir = tmp_path / ".dual-ai-collab"
    config_dir.mkdir(exist_ok=True)
    # 写入 model-routing.json（model_router.py 使用）
    routing_config = {
        "model_routing": {
            "quick": {"adapter": "deepseek-cli", "reason": "快速任务使用轻量模型"},
            "normal": {"adapter": "claude-cli", "reason": "正常任务使用标准模型"},
            "heavy": {"adapter": "codex", "reason": "重任务使用最强模型"},
        },
        "fallback_chain": {
            "deepseek-cli": ["claude-cli", "codex"],
            "claude-cli": ["codex"],
            "codex": [],
        },
        "adapter_commands": {
            "deepseek-cli": ["test-adapter-quick", "exec", "-"],
            "claude-cli": ["test-adapter-normal", "exec", "-"],
            "codex": ["test-adapter-heavy", "exec", "-"]
        },
    }
    (config_dir / "model-routing.json").write_text(json.dumps(routing_config, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写入 config.json（其他模块可能使用）
    (config_dir / "config.json").write_text(json.dumps(CONFIG_JSON, ensure_ascii=False, indent=2), encoding="utf-8")


def _setup_stub_adapter(tmp_path: Path, name: str) -> None:
    """创建一个模拟适配器可执行文件"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(STUB_ADAPTER, encoding="utf-8")
    stub.chmod(0o755)
    return stub


@pytest.mark.skipif(os.name == "nt", reason="stub adapter 使用 shebang 脚本")
def test_adapter_backend_routing(tmp_path, monkeypatch):
    """测试 adapter backend 的路由功能"""
    monkeypatch.chdir(tmp_path)
    _write_board(tmp_path)
    _write_config(tmp_path)

    # 创建模拟适配器
    adapter_quick = _setup_stub_adapter(tmp_path, "test-adapter-quick")
    adapter_normal = _setup_stub_adapter(tmp_path, "test-adapter-normal")
    adapter_heavy = _setup_stub_adapter(tmp_path, "test-adapter-heavy")

    # 将 bin 目录添加到 PATH
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")

    # 测试快速任务路由到 test-quick 适配器
    prompt = "测试任务"
    run_task.cmd_start("101", prompt, "adapter", str(tmp_path))

    # 等待任务完成
    deadline = time.time() + 10
    while time.time() < deadline:
        record = read_run_record("101")
        status = run_task._status_adapter(record)
        if status["status"] != "running":
            break
        time.sleep(0.2)

    assert status["status"] == "success"
    assert record["backend"] == "adapter"
    assert record["adapter"] == "deepseek-cli"
    assert status["result"]["result"] == "DONE"

    # 验证日志中包含适配器信息
    log = Path(record["log_file"]).read_text(encoding="utf-8")
    assert "ADAPTER_ARGS" in log
    # 命令格式: sys.argv 从 "exec" 开始（argv[0] 是程序名被隐藏）
    assert "exec" in log


@pytest.mark.skipif(os.name == "nt", reason="stub adapter 使用 shebang 脚本")
def test_adapter_fallback_on_unavailable(tmp_path, monkeypatch):
    """测试适配器不可用时的回退机制"""
    monkeypatch.chdir(tmp_path)
    _write_board(tmp_path)
    _write_config(tmp_path)

    # 只创建 test-heavy 适配器，quick 和 normal 不可用
    adapter_heavy = _setup_stub_adapter(tmp_path, "test-adapter-heavy")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")

    # 启动快速任务，期望回退到 heavy
    prompt = "测试回退"
    run_task.cmd_start("101", prompt, "adapter", str(tmp_path))

    # 等待任务完成
    deadline = time.time() + 10
    while time.time() < deadline:
        record = read_run_record("101")
        status = run_task._status_adapter(record)
        if status["status"] != "running":
            break
        time.sleep(0.2)

    assert status["status"] == "success"
    # deepseek-cli 不可用，应该回退到 claude-cli，claude-cli 不可用再回退到 codex
    assert record["adapter"] == "codex"


@pytest.mark.skipif(os.name == "nt", reason="stub adapter 使用 shebang 脚本")
def test_adapter_no_fallback_fails(tmp_path, monkeypatch):
    """测试所有适配器都不可用时失败"""
    monkeypatch.chdir(tmp_path)
    _write_board(tmp_path)
    _write_config(tmp_path)

    # 不创建任何适配器
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:{os.environ['PATH']}")

    # Fail synchronously instead of creating a worker known to be unavailable.
    with pytest.raises(CliError, match="没有可用的适配器"):
        run_task.cmd_start("101", "测试失败", "adapter", str(tmp_path))
    assert not (tmp_path / ".dual-ai-collab/logs/task-101.pid").exists()
