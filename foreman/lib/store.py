#!/usr/bin/env python3
"""任务存储逻辑 - 从原 tasks_store.py 提取核心功能。"""

from __future__ import annotations

import fcntl
import json
import math
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_TASKS_MD = "planning/tasks.md"
# 旧版本把数据存在 planning/codex-tasks.json；新文件不存在时从这里读取，下次写入时落到新文件
LEGACY_TASKS_JSON = "codex-tasks.json"


class TaskStoreError(Exception):
    """任务板读写错误"""
    pass


class ManagedTaskError(ValueError):
    """受管任务的状态只能由 execution 流程修改"""


def atomic_write(path: Path, content: str) -> None:
    """原子写入文件"""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def describe_error(error: Exception) -> str:
    """读文件或解析 JSON 出错的原因，写成给人看的样子"""
    if isinstance(error, json.JSONDecodeError):
        return f"第 {error.lineno} 行第 {error.colno} 列：{error.msg}"
    if isinstance(error, UnicodeDecodeError):
        return "不是 UTF-8 编码的文本"
    for kind, reason in ((FileNotFoundError, "文件不存在"), (PermissionError, "没有读写权限"),
                         (IsADirectoryError, "它是目录，不是文件")):
        if isinstance(error, kind):
            return reason
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)


def _normalize_task_num(task_num) -> str:
    """标准化任务编号：001 和 1 视为相同。手工改过的任务板里编号可能是数字"""
    return str(task_num).lstrip("0") or "0"


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


def _priority_rank(value: Any) -> tuple[int, float]:
    """排序位次，小的排前。数字越大越优先；P1 这类写法排在数字之后，P1 先于 P2；其余排最后。"""
    if isinstance(value, str):
        text = value.strip()
        label = re.fullmatch(r"[Pp](\d+)", text)
        if label:
            return (1, float(label.group(1)))
        try:
            value = float(text)
        except ValueError:
            return (2, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return (2, 0.0)
    return (0, -float(value))


def _task_sort_key(task: dict) -> tuple[tuple[int, float], str]:
    """任务排序键"""
    return (_priority_rank(task.get("priority", 1)), str(task.get("id", "")))


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


def _existing_json_path(paths: TaskPaths) -> Path | None:
    """返回实际可读的数据文件：优先新文件，默认文件名时回退到旧的 codex-tasks.json。"""
    if paths.json_path.exists():
        return paths.json_path
    if paths.json_path.name == "tasks.json":
        legacy = paths.json_path.with_name(LEGACY_TASKS_JSON)
        if legacy.exists():
            return legacy
    return None


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
    source = _existing_json_path(resolve_task_paths(task_file))

    if source is None:
        return {"tasks": []}

    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise TaskStoreError(f"任务板 {source} 读不出来（{describe_error(e)}）。"
                             "文件没有被改动；修好 JSON，或从 git、备份恢复它") from e
    tasks = document.get("tasks", []) if isinstance(document, dict) else None
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise TaskStoreError(
            f'任务板 {source} 的结构不对：应是 {{"tasks": [...]}}，其中每个任务是一个 JSON 对象。'
            "文件没有被改动；修好它，或从 git、备份恢复它"
        )

    # 标准化任务
    if migrate:
        for task in tasks:
            _normalize_task(task)

    return document


def write_tasks_document(document: dict, task_file: str | Path = DEFAULT_TASKS_MD, *, sync_markdown: bool = True) -> dict:
    """写入任务文档"""
    paths = resolve_task_paths(task_file)
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)

    with _file_lock(paths.json_path):
        _write_files(document, paths, sync_markdown)

    return document


def _write_files(document: dict, paths: TaskPaths, sync_markdown: bool = True) -> None:
    content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    atomic_write(paths.json_path, content)
    if sync_markdown:
        atomic_write(paths.md_path, render_markdown(document))


def update_tasks_document(task_file: str | Path, mutate) -> Any:
    """在同一把文件锁内读取、修改并写回任务文档，返回 mutate 的结果。

    只锁写入时，并发的“读、改、写”会互相覆盖。mutate 抛出异常时不写入。

    mutate 会被调用两次，所以它只能修改传给它的文档：第一次在加锁之前，用一份不会写回的文档，
    会被拒绝的修改在这里就报错，不必为它创建目录和锁文件。
    """
    paths = resolve_task_paths(task_file)
    mutate(read_tasks_document(task_file))
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(paths.json_path):
        document = read_tasks_document(task_file)
        result = mutate(document)
        _write_files(document, paths)
    return result


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


def dependency_cycles(tasks: list[dict]) -> list[list[str]]:
    """找出依赖环；每个环按依赖方向列出任务 ID，首尾是同一个任务"""
    def key(value) -> str:
        return _normalize_task_num(str(value))

    names = {key(task.get("id", "")): str(task.get("id", "")) for task in tasks}
    graph = {key(task.get("id", "")): [key(dep) for dep in dependency_ids(task.get("dependencies"))]
             for task in tasks}
    state: dict[str, str] = {}
    cycles = []
    for start in graph:
        if start in state:
            continue
        state[start] = "open"
        path, pending = [start], [iter(graph[start])]
        while pending:
            for dep in pending[-1]:
                if state.get(dep) == "open":
                    cycles.append([names[k] for k in [*path[path.index(dep):], dep]])
                elif dep in graph and dep not in state:
                    state[dep] = "open"
                    path.append(dep)
                    pending.append(iter(graph[dep]))
                    break
            else:
                state[path.pop()] = "done"
                pending.pop()
    return cycles


def dependency_satisfied(tasks: list[dict], dep_num: str) -> bool:
    """检查依赖是否满足"""
    for task in tasks:
        if _normalize_task_num(task.get("id", "")) == _normalize_task_num(dep_num):
            status = task.get("status", "")
            # 需要有效的集成确认
            return status == "DONE" and task.get("integration")
    return False


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

GLOB_CHARS = "*?["
READY_STATUSES = {"PENDING", "OPEN", "TODO"}
# 已开始但未提交的工作：占用列出的文件；未列出 files 时范围未知，阻止其他任务并行
ACTIVE_STATUSES = {"IN_PROGRESS", "AWAITING_REVIEW", "AWAITING_INTEGRATION", "REJECTED"}
# 停下等人处理的任务：只占用列出的文件，未列出时不阻止其他任务，避免整个任务板停住
STALLED_STATUSES = {"BLOCKED", "FAILED"}

def _file_scope(path: str) -> str:
    """把文件或目录路径规范成比较用的范围；含通配符时退到所在目录。空字符串表示整个仓库。"""
    scope = str(path).strip().replace("\\", "/")
    while scope.startswith("./"):
        scope = scope[2:]
    for index, char in enumerate(scope):
        if char in GLOB_CHARS:
            scope = scope[:index]
            scope = scope.rsplit("/", 1)[0] if "/" in scope else ""
            break
    return scope.rstrip("/")


def _scopes_overlap(a: str, b: str) -> bool:
    if not a or not b:
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _files_overlap(files_a: list[str], files_b: list[str]) -> tuple[str, str] | None:
    for a in files_a:
        for b in files_b:
            if _scopes_overlap(_file_scope(a), _file_scope(b)):
                return a, b
    return None


def select_parallel_batch(document: dict, roles: dict | None = None, max_parallel: int = 2) -> dict:
    """挑出下一批可以同时执行的待开始任务（PENDING，兼容旧任务板的 OPEN/TODO）。

    条件：依赖已完成；角色已配置（任务写了 role 时）；修改的文件与本批其他任务、
    以及已开始但未完成的任务都不重叠；未列出 files 的任务只能单独执行。
    """
    tasks = document.get("tasks", [])
    roles = roles or {}
    max_parallel = max(1, int(max_parallel))

    holders = []
    for task in tasks:
        status = task.get("status", "PENDING")
        files = list(task.get("files") or [])
        if status in ACTIVE_STATUSES or (status in STALLED_STATUSES and files):
            holders.append((task.get("id"), files))
    batch: list[dict] = []
    skipped: list[dict] = []
    exclusive = False

    pending = [task for task in tasks if task.get("status", "PENDING") in READY_STATUSES]
    for task in sorted(pending, key=_task_sort_key):
        task_id = task.get("id")

        def skip(reason: str, task_id=task_id) -> None:
            skipped.append({"id": task_id, "reason": reason})

        unmet = [dep for dep in dependency_ids(task.get("dependencies")) if not dependency_satisfied(tasks, dep)]
        if unmet:
            skip("依赖未完成: " + ", ".join(f"#{dep}" for dep in unmet))
            continue
        role = task.get("role")
        if role and role not in roles:
            skip(f"角色 {role} 未配置")
            continue
        if exclusive:
            skip("本批已有一个未列出 files 的任务，它需要单独执行")
            continue
        if len(batch) >= max_parallel:
            skip(f"已达到并发上限 {max_parallel}")
            continue

        files = list(task.get("files") or [])
        if not files:
            if batch or holders:
                skip("未列出 files，需要在没有其他进行中任务时单独执行")
                continue
            batch.append(task)
            exclusive = True
            continue

        conflict = None
        for other_id, other_files in holders + [(b.get("id"), list(b.get("files") or [])) for b in batch]:
            if not other_files:
                conflict = f"任务 {other_id} 未列出 files 且尚未完成，不能与它并行"
                break
            overlap = _files_overlap(files, other_files)
            if overlap:
                conflict = f"与任务 {other_id} 的文件重叠: {overlap[0]} ↔ {overlap[1]}"
                break
        if conflict:
            skip(conflict)
            continue
        batch.append(task)

    return {"batch": batch, "skipped": skipped, "max_parallel": max_parallel}
