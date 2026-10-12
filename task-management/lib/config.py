#!/usr/bin/env python3
"""配置管理 - 支持用户自定义 complexity→droid 映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
        }
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config_file = project_root / ".task-management" / "config.json"
        self.config = self._load()

    def _load(self) -> dict:
        """加载配置"""
        if self.config_file.exists():
            try:
                return json.loads(self.config_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return self.DEFAULT_CONFIG.copy()

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
        return self.config.copy()
