"""Planning-time check: report for the whole board what execution would reject or never reach."""

from __future__ import annotations

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


def check_plan(root: Path) -> dict:
    root = Path(root).resolve()
    tasks = TaskBoard.load(root).get_all_tasks()
    config = ExecutionConfig(root)
    board: list[dict] = []
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
    for cycle in dependency_cycles(tasks):
        problem(cycle[0], "dependencies", "依赖成环：" + " → ".join(cycle))

    team = [{"role": role, "tasks": ids,
             "problem": f"角色尚未配置模型；运行 foreman team set {role} --model <模型ID> --description <职责>"}
            for role, ids in unready.items()]
    return {"ok": not board and not team, "checked": checked, "direct": direct, "board": board, "team": team}
