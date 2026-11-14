from __future__ import annotations

import os
from pathlib import Path

import pytest

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

from config import load_config  # noqa: E402


def test_load_config_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config["default_backend"] == "direct"
    assert config["default_sandbox"] == "workspace-write"
    assert config["log_level"] == "INFO"


def test_load_config_from_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".dual-ai-collab"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"default_sandbox": "read-only", "log_level": "DEBUG"}', encoding="utf-8")

    config = load_config()
    assert config["default_sandbox"] == "read-only"
    assert config["log_level"] == "DEBUG"
    assert config["default_backend"] == "direct"


def test_load_config_env_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUAL_AI_DEFAULT_SANDBOX", "danger-full-access")
    monkeypatch.setenv("DUAL_AI_LOG_LEVEL", "ERROR")

    config = load_config()
    assert config["default_sandbox"] == "danger-full-access"
    assert config["log_level"] == "ERROR"


def test_load_config_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".dual-ai-collab"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"default_sandbox": "read-only"}', encoding="utf-8")

    monkeypatch.setenv("DUAL_AI_DEFAULT_SANDBOX", "workspace-write")

    config = load_config()
    assert config["default_sandbox"] == "workspace-write"
