#!/usr/bin/env python3
"""配置管理 - 支持环境变量和配置文件。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _config_file_path() -> Path:
    """Return config file path relative to current working directory."""
    return Path.cwd() / ".dual-ai-collab" / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from file and environment variables.

    Priority: Environment variables > config file > defaults.
    """
    config = {
        "default_sandbox": "workspace-write",
        "default_backend": "direct",
        "codex_bin": "codex",
        "log_level": "INFO",
        "enable_structured_logs": True,
        "process_check_cache_ttl": 0.5,
        "model_routing": {
            "quick": {"adapter": "deepseek-cli", "fallback": "claude-cli"},
            "normal": {"adapter": "claude-cli", "fallback": "codex"},
            "heavy": {"adapter": "codex", "fallback": "claude-cli"},
        },
        "adapter_commands": {
            "deepseek-cli": ["deepseek", "exec", "-"],
            "claude-cli": ["claude", "exec", "-"],
            "codex": ["codex", "exec", "-"],
        },
    }

    # Load from config file
    config_path = _config_file_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
        except (OSError, json.JSONDecodeError):
            pass

    # Override with environment variables
    env_mappings = {
        "DUAL_AI_DEFAULT_SANDBOX": "default_sandbox",
        "DUAL_AI_DEFAULT_BACKEND": "default_backend",
        "CODEX_BIN": "codex_bin",
        "DUAL_AI_LOG_LEVEL": "log_level",
        "DUAL_AI_STRUCTURED_LOGS": ("enable_structured_logs", lambda v: v.lower() in ("1", "true", "yes")),
        "DUAL_AI_PROCESS_CACHE_TTL": ("process_check_cache_ttl", float),
    }

    for env_key, mapping in env_mappings.items():
        value = os.environ.get(env_key)
        if value is not None:
            if isinstance(mapping, tuple):
                config_key, converter = mapping
                try:
                    config[config_key] = converter(value)
                except (ValueError, TypeError):
                    pass
            else:
                config[mapping] = value

    return config


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = _config_file_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a single config value."""
    config = load_config()
    return config.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """Set a single config value and save."""
    config = load_config()
    config[key] = value
    save_config(config)
