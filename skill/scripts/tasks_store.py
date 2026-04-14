#!/usr/bin/env python3
"""任务板存储层：以 tasks.json 为真相源，Markdown 作为渲染视图。"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path


FIELD_LABELS = {
    "priority": "优先级",
    "status": "状态",
    "assigned_to": "分配给",
    "dependencies": "依赖任务",
    "execution_level": "执行级别",
    "stall_threshold_minutes": "卡死阈值",
}
LABEL_TO_KEY = {value: key for key, value in FIELD_LABELS.items()}
DEFAULT_TASKS_JSON = "planning/tasks.json"
DEFAULT_TASKS_MD = "planning/codex-tasks.md"


class CliError(Exception):
    """面向 CLI 的可预期错误。"""


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _normalize_task_num(task_num: str) -> str:
    stripped = task_num.lstrip("0")
    return stripped or "0"


def _normalize_stall_value(value: str) -> str:
    match = re.fullmatch(r"(\d+)(?:m)?", value.strip())
    return match.group(1) if match else value.strip()


def _extract_commands_from_text(text: str) -> list[str]:
    return [match.strip() for match in re.findall(r"`([^`]+)`", text)]


def _task_sort_key(task: dict) -> tuple[int, str]:
    match = re.match(r"P(\d)", task.get("priority", "P9"))
    priority = int(match.group(1)) if match else 9
    return priority, task.get("id", "")


@dataclass
class TaskPaths:
    markdown_path: Path
    json_path: Path


def resolve_task_paths(task_file: str | Path = DEFAULT_TASKS_MD) -> TaskPaths:
    path = Path(task_file)
    if path.suffix.lower() == ".json":
        return TaskPaths(markdown_path=path.with_name(DEFAULT_TASKS_MD.split("/")[-1]), json_path=path)
    if path.suffix.lower() == ".md":
        return TaskPaths(markdown_path=path, json_path=path.with_name("tasks.json"))
    return TaskPaths(markdown_path=Path(DEFAULT_TASKS_MD), json_path=Path(DEFAULT_TASKS_JSON))


def _default_document(paths: TaskPaths) -> dict:
    return {
        "version": 1,
        "markdown_path": str(paths.markdown_path),
        "json_path": str(paths.json_path),
        "header": "",
        "tasks": [],
    }


def _normalize_task(task: dict) -> dict:
    result = deepcopy(task)
    result["id"] = str(result.get("id", "")).strip()
    result["title"] = str(result.get("title", "")).strip()
    result["priority"] = str(result.get("priority", "P9") or "P9").strip()
    result["status"] = str(result.get("status", "")).strip()
    result["status_explicit"] = bool(result.get("status_explicit", bool(result["status"])))
    result["assigned_to"] = str(result.get("assigned_to", "")).strip()
    result["dependencies"] = str(result.get("dependencies", "无") or "无").strip()
    result["execution_level"] = str(result.get("execution_level", "") or "").strip()
    stall_value = str(result.get("stall_threshold_minutes", "") or "").strip()
    result["stall_threshold_minutes"] = _normalize_stall_value(stall_value) if stall_value else ""
    result["field_order"] = [entry for entry in result.get("field_order", []) if entry]
    result["extra_fields"] = deepcopy(result.get("extra_fields", {}))
    sections = []
    for section in result.get("sections", []):
        heading = str(section.get("heading", "")).strip()
        body = str(section.get("body", "")).rstrip()
        if heading:
            sections.append({"heading": heading, "body": body})
    result["sections"] = sections
    result["acceptance_commands"] = []
    for section in sections:
        if section["heading"] == "验收标准":
            result["acceptance_commands"].extend(_extract_commands_from_text(section["body"]))
    return result


def normalize_document(document: dict, paths: TaskPaths) -> dict:
    normalized = _default_document(paths)
    normalized["version"] = int(document.get("version", 1))
    normalized["markdown_path"] = str(paths.markdown_path)
    normalized["json_path"] = str(paths.json_path)
    normalized["header"] = str(document.get("header", "")).rstrip()
    normalized["tasks"] = [_normalize_task(task) for task in document.get("tasks", [])]
    return normalized


def parse_markdown(markdown_text: str, paths: TaskPaths) -> dict:
    document = _default_document(paths)
    lines = markdown_text.splitlines()
    header_lines: list[str] = []
    tasks: list[dict] = []
    current: dict | None = None
    current_section: dict | None = None

    def flush_current() -> None:
        nonlocal current, current_section
        if current is None:
            return
        if current_section is not None:
            current["sections"].append(
                {
                    "heading": current_section["heading"],
                    "body": "\n".join(current_section["lines"]).rstrip(),
                }
            )
        current_section = None
        tasks.append(_normalize_task(current))
        current = None

    for line in lines:
        match = re.match(r"^## 任务 #(\d+):\s*(.*)", line)
        if match:
            flush_current()
            current = {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "priority": "P9",
                "status": "",
                "status_explicit": False,
                "assigned_to": "",
                "dependencies": "无",
                "execution_level": "",
                "stall_threshold_minutes": "",
                "field_order": [],
                "extra_fields": {},
                "sections": [],
            }
            continue

        if current is None:
            header_lines.append(line)
            continue

        if line.strip() == "---":
            flush_current()
            continue

        field_match = re.match(r"^\*\*(.+?)\*\*:\s*(.*)", line)
        if field_match and current_section is None:
            label = field_match.group(1).strip()
            raw_value = field_match.group(2).strip()
            key = LABEL_TO_KEY.get(label)
            if key:
                current[key] = _normalize_stall_value(raw_value) if key == "stall_threshold_minutes" else raw_value
                current["field_order"].append(key)
                if key == "status":
                    current["status_explicit"] = True
            else:
                current["extra_fields"][label] = raw_value
                current["field_order"].append(f"extra:{label}")
            continue

        section_match = re.match(r"^###\s+(.+)", line)
        if section_match:
            if current_section is not None:
                current["sections"].append(
                    {
                        "heading": current_section["heading"],
                        "body": "\n".join(current_section["lines"]).rstrip(),
                    }
                )
            current_section = {"heading": section_match.group(1).strip(), "lines": []}
            continue

        if current_section is not None:
            current_section["lines"].append(line)

    flush_current()
    document["header"] = "\n".join(header_lines).rstrip()
    document["tasks"] = tasks
    return document


def render_markdown(document: dict) -> str:
    lines: list[str] = []
    header = str(document.get("header", "")).rstrip()
    if header:
        lines.append(header)
        lines.append("")

    for task in document.get("tasks", []):
        task = _normalize_task(task)
        lines.append(f"## 任务 #{task['id']}: {task['title']}")
        lines.append("")

        field_order = task.get("field_order") or ["priority", "status", "assigned_to", "dependencies"]
        seen: set[str] = set()
        for entry in field_order:
            seen.add(entry)
            if entry.startswith("extra:"):
                label = entry.split(":", 1)[1]
                if label in task["extra_fields"]:
                    lines.append(f"**{label}**: {task['extra_fields'][label]}")
                continue

            if entry == "priority" and task["priority"] == "P9":
                continue
            if entry == "status" and not task["status_explicit"]:
                continue
            value = task.get(entry, "")
            if value in ("", None):
                continue
            label = FIELD_LABELS[entry]
            if entry == "stall_threshold_minutes":
                value = f"{value}m"
            lines.append(f"**{label}**: {value}")

        for default_key in ("priority", "status", "assigned_to", "dependencies", "execution_level", "stall_threshold_minutes"):
            if default_key in seen:
                continue
            if default_key == "priority" and task["priority"] == "P9":
                continue
            if default_key == "status" and not task["status_explicit"]:
                continue
            value = task.get(default_key, "")
            if value in ("", None):
                continue
            label = FIELD_LABELS[default_key]
            if default_key == "stall_threshold_minutes":
                value = f"{value}m"
            lines.append(f"**{label}**: {value}")

        for section in task.get("sections", []):
            lines.append("")
            lines.append(f"### {section['heading']}")
            body = section.get("body", "")
            if body:
                lines.extend(body.splitlines())

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def read_tasks_document(task_file: str | Path = DEFAULT_TASKS_MD) -> dict:
    paths = resolve_task_paths(task_file)
    if paths.json_path.exists():
        try:
            with open(paths.json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError(f"任务 JSON 无法读取: {paths.json_path} ({exc})") from exc
        return normalize_document(data, paths)

    if not paths.markdown_path.exists():
        raise CliError(f"任务板不存在: {task_file}")

    markdown = paths.markdown_path.read_text(encoding="utf-8")
    document = parse_markdown(markdown, paths)
    atomic_write(paths.json_path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return document


def write_tasks_document(document: dict, task_file: str | Path = DEFAULT_TASKS_MD, *, sync_markdown: bool = True) -> dict:
    paths = resolve_task_paths(task_file)
    normalized = normalize_document(document, paths)
    atomic_write(paths.json_path, json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    if sync_markdown:
        atomic_write(paths.markdown_path, render_markdown(normalized))
    return normalized


def find_task(document: dict, task_num: str) -> dict | None:
    target = _normalize_task_num(task_num)
    for task in document.get("tasks", []):
        if _normalize_task_num(task.get("id", "")) == target:
            return task
    return None


def require_explicit_status(task: dict, task_file: str) -> None:
    if task.get("status_explicit"):
        return
    raise CliError(f"任务 #{task['id']} 缺少 `**状态**` 字段，无法继续处理: {task_file}")


def has_dependencies(deps: str) -> bool:
    return bool(deps) and deps not in ("无", "-", "")


def dependency_satisfied(tasks: list[dict], dep_num: str) -> bool:
    target = _normalize_task_num(dep_num)
    for task in tasks:
        if _normalize_task_num(task.get("id", "")) == target:
            return task.get("status") in ("DONE", "VERIFIED")
    return False


def all_dependencies_satisfied(tasks: list[dict], deps: str) -> bool:
    if not has_dependencies(deps):
        return True
    return all(dependency_satisfied(tasks, match.group(1)) for match in re.finditer(r"#(\d+)", deps))


def resolve_stall_minutes(task: dict | None) -> int:
    if not task:
        return 3
    stall = str(task.get("stall_threshold_minutes", "")).strip()
    if stall:
        try:
            return int(stall)
        except ValueError:
            pass
    level = task.get("execution_level", "")
    return {"heavy": 10, "normal": 5, "quick": 3}.get(level, 3)


def open_tasks_sorted(document: dict) -> list[dict]:
    return sorted(
        [task for task in document.get("tasks", []) if task.get("status") == "OPEN"],
        key=_task_sort_key,
    )


def report_missing_status(tasks: list[dict]) -> list[dict]:
    valid = []
    for task in tasks:
        if task.get("status_explicit"):
            valid.append(task)
        else:
            print(
                f"WARNING: 任务 #{task['id']} 缺少 `**状态**` 字段，已从统计中排除",
                file=sys.stderr,
            )
    return valid


def extract_acceptance_commands(task: dict) -> list[str]:
    commands: list[str] = []
    for section in task.get("sections", []):
        if section.get("heading") == "验收标准":
            commands.extend(_extract_commands_from_text(section.get("body", "")))
    return commands
