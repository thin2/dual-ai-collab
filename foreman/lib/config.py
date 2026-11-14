#!/usr/bin/env python3
"""配置管理 - complexity→droid 映射、角色→固定模型 droid 映射、并行与重试上限。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

try:
    from .store import describe_error
except ImportError:
    from store import describe_error


class ConfigError(ValueError):
    """配置文件存在，但内容不能用"""


class ExecutionConfig:
    """执行配置管理器"""

    DEFAULT_CONFIG = {
        "execution": {
            "light": "worker",
            "medium": "worker",
            "heavy": "worker"
        },
        "complexity_rules": {
            "by_type": {
                "docs": "light",
                "test": "light",
                "bugfix": "medium",
                "feature": "medium",
                "refactor": "heavy",
                "architecture": "heavy"
            },
            "by_hours": {
                "<=1": "light",
                "<=3": "medium",
                ">3": "heavy"
            }
        },
        "roles": {},
        "parallel": {
            "max_parallel": 2,
            "max_retries": 2
        }
    }
    # parallel 各项允许的最小值
    MINIMUMS = {"max_parallel": 1, "max_retries": 0}

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config_file = project_root / ".task-management" / "config.json"
        self.config = self._load()

    def _load(self) -> dict:
        """加载配置；缺失的顶层项用默认值补齐"""
        config = copy.deepcopy(self.DEFAULT_CONFIG)
        if not self.config_file.exists():
            return config
        # 读不出来的文件不能当成空配置：之后任何一次保存都会用默认值盖掉里面的角色
        try:
            loaded = json.loads(self.config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigError(self._unusable(describe_error(error))) from error
        if not isinstance(loaded, dict):
            raise ConfigError(self._unusable("内容应是 JSON 对象"))
        for key, value in loaded.items():
            if isinstance(config.get(key), dict):
                if not isinstance(value, dict):
                    raise ConfigError(self._unusable(f"{key} 应是 JSON 对象"))
                config[key].update(value)
            else:
                config[key] = value
        for role, entry in config["roles"].items():
            if not isinstance(entry, dict):
                raise ConfigError(self._unusable(f"roles.{role} 应是 JSON 对象"))
        return config

    def _unusable(self, reason: str) -> str:
        return (f"配置文件 {self.config_file} 无法使用（{reason}）。文件没有被改动，里面可能有角色配置；"
                "修好后重试。确认不需要其中的内容时，删除它再运行 foreman init 生成默认配置")

    def save(self) -> None:
        """保存配置"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.config, ensure_ascii=False, indent=2) + "\n"
        self.config_file.write_text(content, encoding="utf-8")

    def get_droid_for_complexity(self, complexity: str) -> str:
        """根据 complexity 获取要使用的 droid"""
        return self.config["execution"].get(complexity, "worker")

    def set_droid_for_complexity(self, complexity: str, droid: str) -> None:
        """设置 complexity 对应的 droid"""
        self.config["execution"][complexity] = droid
        self.save()

    def get_roles(self) -> dict[str, dict]:
        """获取所有角色配置：role → {droid, model, description, read_only}"""
        return copy.deepcopy(self.config.get("roles", {}))

    def get_role(self, role: str) -> dict | None:
        entry = self.config.get("roles", {}).get(role)
        return copy.deepcopy(entry) if entry else None

    def set_role(self, role: str, entry: dict) -> None:
        self.config.setdefault("roles", {})[role] = entry
        self.save()

    def remove_role(self, role: str) -> bool:
        removed = self.config.get("roles", {}).pop(role, None) is not None
        if removed:
            self.save()
        return removed

    def _limit(self, name: str) -> int:
        value = self.config["parallel"].get(name, self.DEFAULT_CONFIG["parallel"][name])
        try:
            return max(self.MINIMUMS[name], int(value))
        except (TypeError, ValueError):
            raise ConfigError(f"配置 parallel.{name} 应是整数，现在是 {value!r}；"
                              f"用 foreman config set parallel.{name}=<数字> 修正") from None

    def get_max_parallel(self) -> int:
        return self._limit("max_parallel")

    def get_max_retries(self) -> int:
        return self._limit("max_retries")

    def determine_complexity(self, task: dict) -> str:
        """
        确定任务的复杂度

        优先级：
        1. 显式 execution_level 字段
        2. 任务类型匹配规则
        3. 预估时间匹配规则
        4. 默认值 medium
        """
        # 方法一：显式指定
        if "execution_level" in task:
            level_map = {"quick": "light", "normal": "medium", "heavy": "heavy"}
            return level_map.get(task["execution_level"], "medium")

        # 方法二：根据类型
        task_type = task.get("type", "")
        if task_type in self.config["complexity_rules"]["by_type"]:
            return self.config["complexity_rules"]["by_type"][task_type]

        # 方法三：根据预估时间
        hours = task.get("estimated_hours", 2)
        if hours <= 1:
            return "light"
        elif hours <= 3:
            return "medium"
        else:
            return "heavy"

    def get_all_settings(self) -> dict:
        """获取所有配置"""
        return copy.deepcopy(self.config)
