#!/usr/bin/env python3
"""任务存储逻辑 - 从原 tasks_store.py 提取核心功能。"""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_TASKS_MD = "planning/codex-tasks.md"


class CliError(Exception):
    """CLI 错误"""
    pass


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件"""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def _normalize_task_num(task_num: str) -> str:
    """标准化任务编号：001 和 1 视为相同"""
    return task_num.lstrip("0") or "0"


def _extract_commands_from_text(text: str) -> list[str]:
    """从文本中提取反引号包围的命令"""
    commands = []
    in_code_block = False
    code_block_lines = []
    
    for line in text.split("\n"):
        stripped = line.strip()
        
        # 检测代码块边界
        if stripped.startswith("```"):
            if in_code_block:
                # 结束代码块
                if code_block_lines:
                    commands.append("\n".join(code_block_lines))
                code_block_lines = []
            in_code_block = not in_code_block
            continue
        
        # 代码块内的行
        if in_code_block:
            code_block_lines.append(line)
            continue
        
        # 行内代码：提取反引号包围的内容
        matches = re.findall(r"`([^`]+)`", stripped)
        commands.extend(matches)
    
    return [cmd.strip() for cmd in commands if cmd.strip()]


def _task_sort_key(task: dict) -> tuple[int, str]:
    """任务排序键"""
    priority = task.get("priority", 1)
    task_id = task.get("id", "")
    return (-priority, task_id)


class TaskPaths:
    """任务文件路径"""
    def __init__(self, json_path: Path, md_path: Path):
        self.json_path = json_path
        self.md_path = md_path


def resolve_task_paths(task_file: str | Path = DEFAULT_TASKS_MD) -> TaskPaths:
    """解析任务文件路径"""
    md_path = Path(task_file).resolve()
    json_path = md_path.with_suffix(".json")
    return TaskPaths(json_path, md_path)


@contextmanager
def _file_lock(path: Path):
    """文件锁"""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(lock_path, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_tasks_document(task_file: str | Path = DEFAULT_TASKS_MD, *, migrate: bool = True) -> dict:
    """读取任务文档"""
    paths = resolve_task_paths(task_file)
    
    if not paths.json_path.exists():
        return {"tasks": []}
    
    try:
        document = json.loads(paths.json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CliError(f"Failed to read tasks: {e}")
    
    # 标准化任务
    if migrate:
        for task in document.get("tasks", []):
            _normalize_task(task)
    
    return document


def write_tasks_document(document: dict, task_file: str | Path = DEFAULT_TASKS_MD, *, sync_markdown: bool = True) -> dict:
    """写入任务文档"""
    paths = resolve_task_paths(task_file)
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    
    with _file_lock(paths.json_path):
        # 写入 JSON
        content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        atomic_write(paths.json_path, content)
        
        # 同步 Markdown
        if sync_markdown:
            md_content = render_markdown(document)
            atomic_write(paths.md_path, md_content)
    
    return document


def _normalize_task(task: dict) -> dict:
    """标准化任务字段（向后兼容）"""
    # task_num → id
    if "task_num" in task and "id" not in task:
        task["id"] = task["task_num"]
    
    # 确保 id 存在
    if "id" not in task:
        task["id"] = "UNKNOWN"
    
    # 依赖格式：列表 → 字符串
    if "dependencies" in task and isinstance(task["dependencies"], list):
        deps = task["dependencies"]
        if deps:
            task["dependencies"] = ", ".join(f"#{d}" for d in deps)
        else:
            task["dependencies"] = "无"
    
    return task


def render_markdown(document: dict) -> str:
    """渲染任务板为 Markdown"""
    lines = ["# 任务板", ""]
    
    for task in document.get("tasks", []):
        lines.append(f"## 任务 {task['id']}: {task.get('title', '未命名')}")
        lines.append("")
        lines.append(f"**状态**: {task.get('status', 'PENDING')}")
        lines.append(f"**优先级**: {task.get('priority', 1)}")
        lines.append(f"**类型**: {task.get('type', 'feature')}")
        lines.append(f"**预估时间**: {task.get('estimated_hours', 0)}小时")
        lines.append(f"**依赖**: {task.get('dependencies', '无')}")
        lines.append("")
        
        # 渲染 sections
        for section in task.get("sections", []):
            heading = section.get("heading", "")
            body = section.get("body", "")
            if heading:
                lines.append(f"### {heading}")
                lines.append("")
            if body:
                lines.append(body)
                lines.append("")
        
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


def find_task(document: dict, task_num: str) -> dict | None:
    """查找任务"""
    normalized = _normalize_task_num(task_num)
    for task in document.get("tasks", []):
        if _normalize_task_num(task.get("id", "")) == normalized:
            return task
    return None


def dependency_ids(deps) -> list[str]:
    """提取依赖任务 ID"""
    if not deps or deps == "无":
        return []
    
    if isinstance(deps, list):
        return deps
    
    # 字符串格式：#001, #002
    ids = []
    for part in str(deps).split(","):
        part = part.strip().lstrip("#")
        if part and part != "无":
            ids.append(part)
    return ids


def dependency_satisfied(tasks: list[dict], dep_num: str) -> bool:
    """检查依赖是否满足"""
    for task in tasks:
        if _normalize_task_num(task.get("id", "")) == _normalize_task_num(dep_num):
            status = task.get("status", "")
            # 需要有效的集成确认
            return status == "DONE" and task.get("integration")
    return False


def all_dependencies_satisfied(tasks: list[dict], deps) -> bool:
    """检查所有依赖是否满足"""
    dep_list = dependency_ids(deps)
    if not dep_list:
        return True
    return all(dependency_satisfied(tasks, dep) for dep in dep_list)


def executable_tasks(document: dict) -> list[dict]:
    """获取可执行的任务（依赖已满足）"""
    tasks = document.get("tasks", [])
    result = []
    
    for task in tasks:
        status = task.get("status", "PENDING")
        if status in ["DONE", "AWAITING_INTEGRATION"]:
            continue
        if all_dependencies_satisfied(tasks, task.get("dependencies")):
            result.append(task)
    
    return sorted(result, key=_task_sort_key)


def open_tasks_sorted(document: dict) -> list[dict]:
    """获取所有未完成的任务（按优先级排序）"""
    tasks = document.get("tasks", [])
    open_tasks = [t for t in tasks if t.get("status") not in ["DONE"]]
    return sorted(open_tasks, key=_task_sort_key)


def extract_acceptance_commands(task: dict) -> list[str]:
    """从任务中提取验收命令"""
    commands = []
    
    for section in task.get("sections", []):
        heading = section.get("heading", "")
        if "验收" in heading or "acceptance" in heading.lower():
            body = section.get("body", "")
            commands.extend(_extract_commands_from_text(body))
    
    return commands
