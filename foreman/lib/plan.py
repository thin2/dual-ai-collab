"""Planning-time check: report for the whole board what execution would reject or never reach."""

from __future__ import annotations

import re
from pathlib import Path

from .board import TaskBoard
from .config import ExecutionConfig
from .store import (
    ACTIVE_STATUSES,
    READY_STATUSES,
    STALLED_STATUSES,
    _normalize_task_num,
    dependency_cycles,
    dependency_ids,
    dependency_satisfied,
)
from .workflow import declared_path, requirements, runtime_dependencies, task_files

FINISHED_STATUSES = {"DONE", "VERIFIED"}
KNOWN_STATUSES = READY_STATUSES | ACTIVE_STATUSES | STALLED_STATUSES | FINISHED_STATUSES


def _dispatch_problems(root: Path, task: dict) -> list[tuple[str, str]]:
    """The same validators begin and accept run, so this report cannot drift from them."""
    problems = []
    for field, declared in (("files", task_files), ("runtime_dependencies", runtime_dependencies)):
        try:
            for path in declared(task):
                declared_path(root, path)
        except ValueError as error:
            problems.append((field, str(error)))
    try:
        requirements(task)
    except ValueError as error:
        problems.append(("acceptance", str(error)))
    return problems


# A task is meant to be done, accepted and rolled back in one piece.
MAX_HOURS = 3
MAX_FILES = 10
MAX_RESULTS = 2
# A folder that names a platform decides the layer; otherwise the file type does.
LAYER_FOLDERS = {"ios": "iOS 原生", "android": "Android 原生", "web": "Web 前端", "frontend": "Web 前端",
                 "backend": "服务端", "server": "服务端"}
LAYER_SUFFIXES = {
    "Web 前端": {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".css", ".scss", ".less"},
    "iOS 原生": {".swift", ".m", ".mm", ".xib", ".storyboard"},
    "Android 原生": {".kt", ".kts"},
}


def _layer(path: str) -> str | None:
    parts = Path(path).parts
    for part in parts:
        if part.lower() in LAYER_FOLDERS:
            return LAYER_FOLDERS[part.lower()]
    suffix = Path(path).suffix.lower()
    return next((layer for layer, suffixes in LAYER_SUFFIXES.items() if suffix in suffixes), None)


def _results(expected: str) -> int:
    """How many separate outcomes one expected text lists: clauses, or the items of a numbered list."""
    clauses = [part for part in re.split(r"[；;\n]+", expected) if part.strip()]
    numbered = re.findall(r"(?:^|[\s，,；;：:])\d+[.、)）](?!\d)|[（(]\d+[)）]", expected)
    return max(len(clauses), len(numbered))


def _size_warnings(task: dict) -> list[tuple[str, str]]:
    """Signs that a task is too large to accept or roll back in one piece. None of them stops execution."""
    found = []
    hours = task.get("estimated_hours")
    if isinstance(hours, (int, float)) and not isinstance(hours, bool) and hours > MAX_HOURS:
        found.append(("estimated_hours", f"预估 {hours:g} 小时，超过 {MAX_HOURS} 小时；拆成 1 到 {MAX_HOURS} 小时能做完的任务"))
    files = task.get("files")
    if isinstance(files, list) and all(isinstance(path, str) for path in files):
        if len(files) > MAX_FILES:
            found.append(("files", f"列了 {len(files)} 项，超过 {MAX_FILES} 项；一次验收和回滚的范围太大，按功能拆开"))
        layers: dict[str, str] = {}
        for path in files:
            layers.setdefault(_layer(path) or "", path)
        layers.pop("", None)
        if len(layers) > 1:
            found.append(("files", "同时改 " + "、".join(f"{layer}（{path}）" for layer, path in layers.items())
                          + "；每一层单独一个任务，先定好它们之间的接口"))
    checks = task.get("acceptance")
    for check in checks if isinstance(checks, list) else []:
        expected = check.get("expected") if isinstance(check, dict) else None
        if isinstance(expected, str) and _results(expected) > MAX_RESULTS:
            found.append(("acceptance", f"{check.get('id')} 的 expected 写了 {_results(expected)} 个结果；"
                          "一项验收条件只写一个可观察的结果，其余拆成单独的条件"))
    return found


def check_plan(root: Path) -> dict:
    root = Path(root).resolve()
    tasks = TaskBoard.load(root).get_all_tasks()
    config = ExecutionConfig(root)
    board: list[dict] = []
    warnings: list[dict] = []
    unready: dict[str, list[str]] = {}
    direct: list[str] = []

    def problem(task_id: str, field: str, text: str) -> None:
        board.append({"task": task_id, "field": field, "problem": text})

    if not tasks:
        problem("", "tasks", "任务板没有任务")
    by_key: dict[str, dict] = {}
    for task in tasks:
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip() or task_id == "UNKNOWN":
            problem(str(task_id), "id", "缺少字符串形式的任务编号")
            continue
        key = _normalize_task_num(task_id)
        if key in by_key:
            problem(task_id, "id", f"编号与任务 {by_key[key]['id']} 重复")
            continue
        by_key[key] = task

    checked = []
    for task in by_key.values():
        task_id, status = task["id"], task.get("status", "PENDING")
        known = isinstance(status, str) and status in KNOWN_STATUSES
        if known and status in FINISHED_STATUSES:
            continue
        checked.append(task_id)
        if not known:
            problem(task_id, "status", f"状态 {status} 无效，任务不会被挑选；待开始的任务用 PENDING")
        for dep in dependency_ids(task.get("dependencies")):
            target = by_key.get(_normalize_task_num(str(dep)))
            if not target:
                problem(task_id, "dependencies", f"依赖的任务 #{dep} 不存在")
            elif target.get("status") in FINISHED_STATUSES and not dependency_satisfied(tasks, str(dep)):
                problem(task_id, "dependencies",
                        f"依赖 #{dep} 已是 {target['status']} 但没有集成记录，不会解锁；用 integrate 确认")

        role = task.get("role")
        if role is None or role == "":
            direct.append(task_id)
        elif not isinstance(role, str) or not role.strip():
            problem(task_id, "role", "role 必须是角色名；由当前会话直接执行的任务不写这个字段")
        elif not (config.get_role(role) or {}).get("model"):
            unready.setdefault(role, []).append(task_id)
        for field, text in _dispatch_problems(root, task):
            problem(task_id, field, text)
        # Mirrors TaskBoard.build_context: without either, the worker sees only the title.
        if not task.get("description") and not any(
            section.get("heading") and str(section.get("body", "")).strip()
            for section in task.get("sections", [])
        ):
            problem(task_id, "description", "没有任务描述：执行时只能看到标题和验收条件")
        # Once a task has started, splitting it is no longer a planning decision.
        if known and status in READY_STATUSES:
            warnings.extend({"task": task_id, "field": field, "problem": text} for field, text in _size_warnings(task))
    for cycle in dependency_cycles(tasks):
        problem(cycle[0], "dependencies", "依赖成环：" + " → ".join(cycle))

    team = [{"role": role, "tasks": ids,
             "problem": f"角色尚未配置模型；运行 foreman team set {role} --model <模型ID> --description <职责>"}
            for role, ids in unready.items()]
    # Warnings do not make the plan fail: whether to split a task is left to whoever planned it.
    return {"ok": not board and not team, "checked": checked, "direct": direct, "board": board, "team": team,
            "warnings": warnings}
