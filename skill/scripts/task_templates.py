#!/usr/bin/env python3
"""任务板模板和生成器。"""

from __future__ import annotations

import json
import re
import math

from tasks_store import (CliError, DEFAULT_TASKS_MD, dependency_ids, format_dependencies,
                         find_task, read_tasks_document, resolve_task_paths, write_tasks_document)
from platform_utils import FileLock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATES_DIR = Path(".dual-ai-collab/templates")


# 预定义任务模板
TASK_TEMPLATES = {
    "feature": {
        "title": "实现 {feature_name} 功能",
        "priority": "P2",
        "execution_level": "normal",
        "description": "实现 {feature_name} 功能的核心逻辑",
        "technical_requirements": [
            "设计清晰的 API 接口",
            "编写单元测试",
            "更新相关文档",
        ],
        "acceptance_criteria": [
            "功能按需求正常工作",
            "测试覆盖率达到 80% 以上",
            "代码通过 lint 检查",
        ],
    },
    "bugfix": {
        "title": "修复 {bug_description} 问题",
        "priority": "P1",
        "execution_level": "quick",
        "description": "定位并修复 {bug_description} 相关的问题",
        "technical_requirements": [
            "重现问题",
            "定位根本原因",
            "编写回归测试",
        ],
        "acceptance_criteria": [
            "问题不再出现",
            "添加了防止回归的测试",
            "相关文档已更新",
        ],
    },
    "refactor": {
        "title": "重构 {module_name} 模块",
        "priority": "P3",
        "execution_level": "normal",
        "description": "重构 {module_name} 以提高代码质量和可维护性",
        "technical_requirements": [
            "保持功能不变",
            "改进代码结构",
            "增强测试覆盖",
        ],
        "acceptance_criteria": [
            "所有现有测试通过",
            "代码复杂度降低",
            "没有引入新的 bug",
        ],
    },
    "test": {
        "title": "为 {module_name} 添加测试",
        "priority": "P2",
        "execution_level": "quick",
        "description": "为 {module_name} 编写完整的单元测试和集成测试",
        "technical_requirements": [
            "覆盖主要功能路径",
            "包含边界条件测试",
            "测试错误处理",
        ],
        "acceptance_criteria": [
            "测试覆盖率达到 90% 以上",
            "所有测试通过",
            "测试文档完整",
        ],
    },
    "docs": {
        "title": "编写 {topic} 文档",
        "priority": "P3",
        "execution_level": "quick",
        "description": "编写关于 {topic} 的完整文档",
        "technical_requirements": [
            "包含使用示例",
            "API 文档完整",
            "说明常见问题",
        ],
        "acceptance_criteria": [
            "文档内容准确",
            "示例代码可运行",
            "格式规范",
        ],
    },
    "optimization": {
        "title": "优化 {component} 性能",
        "priority": "P2",
        "execution_level": "heavy",
        "description": "分析并优化 {component} 的性能瓶颈",
        "technical_requirements": [
            "性能分析和基准测试",
            "识别瓶颈",
            "实施优化方案",
        ],
        "acceptance_criteria": [
            "性能提升 X%",
            "基准测试通过",
            "没有功能退化",
        ],
    },
}


def create_task_from_template(
    template_name: str,
    task_num: str,
    **kwargs: Any
) -> dict[str, Any]:
    """从模板创建任务。

    Args:
        template_name: 模板名称
        task_num: 任务编号
        **kwargs: 模板变量替换

    Returns:
        任务字典
    """
    if not re.fullmatch(r"[0-9]+", task_num):
        raise CliError("任务编号必须为数字")
    template = (TASK_TEMPLATES[template_name].copy() if template_name in TASK_TEMPLATES
                else load_custom_template(template_name))

    # 替换模板变量
    for key, value in template.items():
        if isinstance(value, str):
            template[key] = value.format(**kwargs)
        elif isinstance(value, list):
            template[key] = [
                item.format(**kwargs) if isinstance(item, str) else item
                for item in value
            ]

    # 添加标准字段
    task = {
        "id": task_num,
        "title": template["title"],
        "priority": template["priority"],
        "status": "OPEN",
        "assigned_to": "Codex",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "estimated_hours": 1,
        "dependencies": "无",
        "execution_level": template["execution_level"],
        "description": template["description"],
        "technical_requirements": template["technical_requirements"],
        "acceptance_criteria": template["acceptance_criteria"],
        "related_files": [],
    }

    task["sections"] = [
        {"heading": "任务描述", "body": task["description"]},
        {"heading": "技术要求", "body": "\n".join("- " + item for item in task["technical_requirements"])},
        {"heading": "验收标准", "body": "\n".join("- " + item for item in task["acceptance_criteria"])},
    ]
    return task


def auto_split_task(task: dict[str, Any], max_hours: float = 3.0) -> list[dict[str, Any]]:
    """自动拆分大任务为多个子任务。

    Args:
        task: 要拆分的任务
        max_hours: 单个任务的最大工时

    Returns:
        拆分后的子任务列表
    """
    if max_hours <= 0:
        raise CliError("max_hours 必须大于 0")
    estimated_hours = task.get("estimated_hours", 1)

    if estimated_hours <= max_hours:
        return [task]

    # 计算需要拆分的数量
    subtask_count = math.ceil(estimated_hours / max_hours)

    subtasks = []
    base_num = str(task.get("id", task.get("task_num", "")))
    if not base_num.isdigit():
        raise CliError("拆分任务需要数字编号")

    # 根据技术要求拆分
    tech_reqs = task.get("technical_requirements", [])
    acceptance = task.get("acceptance_criteria", [])

    items_per_subtask = max(1, len(tech_reqs) // subtask_count)

    for i in range(subtask_count):
        start_idx = i * items_per_subtask
        end_idx = start_idx + items_per_subtask if i < subtask_count - 1 else len(tech_reqs)

        subtask = task.copy()
        subtask.pop("task_num", None)
        subtask["id"] = str(int(base_num) + i).zfill(len(base_num))
        subtask["title"] = f"{task['title']} - 第 {i+1} 部分"
        subtask["estimated_hours"] = estimated_hours / subtask_count
        subtask["technical_requirements"] = tech_reqs[start_idx:end_idx]

        # 第一个子任务依赖原任务的依赖，后续子任务依赖前一个子任务
        if i == 0:
            subtask["dependencies"] = format_dependencies(task.get("dependencies"))
        else:
            subtask["dependencies"] = format_dependencies([subtasks[-1]["id"]])

        subtask["sections"] = [dict(section) for section in task.get("sections", [])]
        for section in subtask["sections"]:
            if section["heading"] == "技术要求":
                section["body"] = "\n".join("- " + item for item in subtask["technical_requirements"])
        subtasks.append(subtask)

    return subtasks


def generate_acceptance_criteria(description: str, task_type: str = "feature") -> list[str]:
    """生成验收标准建议。

    Args:
        description: 任务描述
        task_type: 任务类型

    Returns:
        验收标准列表
    """
    # 基础验收标准
    base_criteria = {
        "feature": [
            "功能按需求正常工作",
            "所有测试通过",
            "代码通过 lint 检查",
            "文档已更新",
        ],
        "bugfix": [
            "问题已修复且不再出现",
            "添加了回归测试",
            "相关文档已更新",
        ],
        "test": [
            "测试覆盖率达标",
            "所有测试通过",
            "测试文档完整",
        ],
        "refactor": [
            "现有功能保持不变",
            "所有测试通过",
            "代码质量指标改善",
        ],
    }

    criteria = base_criteria.get(task_type, base_criteria["feature"]).copy()

    # 根据描述添加特定标准
    if "API" in description or "接口" in description:
        criteria.append("API 文档完整且准确")

    if "性能" in description or "优化" in description:
        criteria.append("性能指标达到预期")

    if "安全" in description:
        criteria.append("通过安全审计")

    return criteria


def save_template(name: str, template: dict[str, Any]) -> None:
    """保存自定义模板。

    Args:
        name: 模板名称
        template: 模板内容
    """
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    if not re.fullmatch(r"[\w-]+", name):
        raise CliError("模板名称只能包含字母、数字、下划线或连字符")
    template_file = TEMPLATES_DIR / f"{name}.json"
    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)


def load_custom_template(name: str) -> dict[str, Any]:
    """加载自定义模板。

    Args:
        name: 模板名称

    Returns:
        模板内容
    """
    if not re.fullmatch(r"[\w-]+", name):
        raise CliError("模板名称只能包含字母、数字、下划线或连字符")
    template_file = TEMPLATES_DIR / f"{name}.json"
    if not template_file.exists():
        raise FileNotFoundError(f"模板不存在: {name}")

    with open(template_file, "r", encoding="utf-8") as f:
        return json.load(f)


def list_templates() -> dict[str, list[str]]:
    """列出所有可用模板。"""
    builtin = list(TASK_TEMPLATES.keys())

    custom = []
    if TEMPLATES_DIR.exists():
        custom = [f.stem for f in TEMPLATES_DIR.glob("*.json")]

    return {
        "builtin": builtin,
        "custom": custom,
    }


def generate_task_board_from_spec(spec_text: str) -> dict[str, Any]:
    """从需求文档生成任务板。

    Args:
        spec_text: 需求文档内容

    Returns:
        任务板数据结构
    """
    # 简单的启发式规则生成任务
    tasks = []

    lines = spec_text.split("\n")
    current_section = None
    task_num = 1

    for line in lines:
        line = line.strip()

        # 检测章节标题
        if line.startswith("##"):
            current_section = line.replace("##", "").strip()

        # 检测功能点（列表项）
        elif line.startswith("-") or line.startswith("*"):
            feature = line.lstrip("-*").strip()

            if len(feature) > 5:  # 过滤太短的项
                task = {
                    "id": f"{task_num:03d}",
                    "title": f"实现{feature}",
                    "priority": "P2",
                    "status": "OPEN",
                    "assigned_to": "Codex",
                    "execution_level": "normal",
                    "estimated_hours": 2,
                    "dependencies": "无",
                    "description": f"实现 {feature} 功能",
                    "section": current_section or "未分类",
                }

                tasks.append(task)
                task_num += 1

    return {
        "metadata": {
            "name": "自动生成任务板",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_tasks": len(tasks),
        },
        "tasks": tasks,
    }


def add_task_to_board(task: dict, task_file: str = DEFAULT_TASKS_MD, dependencies=None) -> dict:
    """Validate and append under the same lock used by status updates."""
    paths = resolve_task_paths(task_file)
    with FileLock(paths.json_path.with_suffix(".json.lock")):
        document = (read_tasks_document(task_file) if paths.json_path.exists() or paths.markdown_path.exists()
                    else {"tasks": []})
        if find_task(document, task["id"]) is not None:
            raise CliError(f"任务编号已存在: {task['id']}")
        deps = dependency_ids(dependencies if dependencies is not None else task.get("dependencies"))
        for dep in deps:
            if int(dep) == int(task["id"]):
                raise CliError("任务不能依赖自身")
            if find_task(document, dep) is None:
                raise CliError(f"依赖任务不存在: #{dep}")
        task = dict(task, dependencies=format_dependencies(deps))
        document["tasks"].append(task)
        # Reject cycles before publishing the new board.
        from task_visualization import detect_circular_dependencies
        if detect_circular_dependencies(document):
            raise CliError("任务板存在循环依赖")
        write_tasks_document(document, task_file)
        return task
