"""Read-only self-check: what in the environment or in the project's data would stop a command from working."""

from __future__ import annotations

import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from .checkpoint import CheckpointManager
from .config import ExecutionConfig
from .history import ExecutionHistory
from .plan import FINISHED_STATUSES
from .store import DEFAULT_TASKS_MD, TaskStoreError, read_tasks_document
from .team import TeamError, list_byok_models
from .web import board_status
from .workflow import under_git

SKILL_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = SKILL_ROOT / "bin" / "foreman"
OK, NOTE, PROBLEM = "ok", "note", "problem"


def skill_version() -> str:
    """The version in SKILL.md's frontmatter, so an installed copy can say which release it is."""
    try:
        frontmatter = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, ValueError, IndexError):
        return "unknown"
    match = re.search(r"^version:\s*(\S+)\s*$", frontmatter, re.MULTILINE)
    return match.group(1) if match else "unknown"


def diagnose(root: Path | None, cwd: Path) -> list[dict]:
    """One entry per thing checked: level, name, detail and, where it helps, what to do.

    root is the project the commands would use, or None when cwd is not inside one.
    Nothing is created or changed, so this is safe to run anywhere.
    """
    items: list[dict] = []

    def report(level: str, name: str, detail: str, fix: str = "") -> None:
        items.append({"level": level, "name": name, "detail": detail, "fix": fix})

    report(OK, "技能", f"foreman {skill_version()}，位于 {SKILL_ROOT}")
    version = ".".join(map(str, sys.version_info[:3]))
    # Not dead code: on an older Python this command still starts, and this is where it says so.
    if sys.version_info >= (3, 9):  # noqa: UP036
        report(OK, "Python", version)
    else:
        report(PROBLEM, "Python", f"{version}，需要 3.9 或更高", "换用更新的 python3")
    git = shutil.which("git")
    if git:
        report(OK, "git", git)
    else:
        report(NOTE, "git", "PATH 里没有 git：delivery 和范围外改动检查用不了，集成只能用 integrate --no-git", "安装 git")
    found = shutil.which("foreman")
    if found and Path(found).resolve() == LAUNCHER.resolve():
        report(OK, "命令", f"foreman 在 PATH 中（{found}）")
    elif found:
        report(NOTE, "命令", f"PATH 里的 foreman 是另一个程序或另一份安装（{found}）；本技能的命令是 {LAUNCHER}",
               "用完整路径运行，或调整 PATH 的顺序")
    else:
        report(NOTE, "命令", f"foreman 不在 PATH 中，用完整路径 {LAUNCHER} 运行",
               f"想直接输入 foreman：ln -s {LAUNCHER} <PATH 里的目录>/foreman")

    tasks: list[dict] = []
    roles: dict = {}
    if root is None:
        report(NOTE, "项目", f"{cwd} 及其上级目录（到 git 仓库根目录为止）没有任务板或配置",
               "新项目运行 foreman init；已有项目先 cd 到它的目录")
    else:
        if git and not under_git(root):
            report(NOTE, "项目", f"{root}，不在 git 仓库里：不检查范围外改动，集成用 foreman integrate <任务ID> --no-git --note <说明>")
        else:
            report(OK, "项目", str(root))
        tasks = _board(root, report)
        roles = _config(root, report)
        _checkpoint(root, report)
        _records(root, tasks, report)
        _web_board(root, report)
    _dispatch(tasks, roles, report)
    return items


def _board(root: Path, report) -> list[dict]:
    try:
        tasks = read_tasks_document(root / DEFAULT_TASKS_MD).get("tasks", [])
    except TaskStoreError as error:
        report(PROBLEM, "任务板", str(error))
        return []
    if not tasks:
        report(NOTE, "任务板", "没有任务", "把任务写成 JSON 后运行 foreman add --file <文件>")
        return []
    counts = Counter(str(task.get("status", "PENDING")) for task in tasks)
    report(OK, "任务板", f"{len(tasks)} 个任务：" + "、".join(f"{status} {count}" for status, count in sorted(counts.items())))
    return tasks


def _config(root: Path, report) -> dict:
    try:
        config = ExecutionConfig(root)
        roles = config.get_roles()
        limits = f"并发上限 {config.get_max_parallel()}，重试上限 {config.get_max_retries()}"
    except ValueError as error:
        report(PROBLEM, "配置", str(error))
        return {}
    source = "" if config.config_file.exists() else "没有配置文件，使用默认值；"
    report(OK, "配置", f"{source}{len(roles)} 个角色，{limits}")
    return roles


def _checkpoint(root: Path, report) -> None:
    try:
        checkpoint = CheckpointManager(root).load()
    except ValueError as error:
        report(PROBLEM, "checkpoint", str(error))
        return
    report(OK, "checkpoint", f"阶段 {checkpoint.get('phase', 'unknown')}" if checkpoint else "没有保存过")


def _records(root: Path, tasks: list[dict], report) -> None:
    history = ExecutionHistory(root)
    folder = history.history_dir
    records, unreadable = history.get_all_history(), history.unreadable
    lost = [f"任务 {task.get('id')} 的 {task['execution_id']}" for task in tasks
            if task.get("execution_id") and not (folder / f"{task['execution_id']}.json").is_file()]
    running = [record.execution_id or record.task_id for record in records if record.status == "running"]
    if unreadable:
        report(PROBLEM, "执行记录", f"{len(unreadable)} 个读不出来（在 {folder} 下）：{'、'.join(unreadable)}",
               "修好 JSON，或从 git、备份恢复")
    if lost:
        report(PROBLEM, "执行记录", "任务板登记的记录不存在：" + "；".join(lost), f"把记录文件恢复到 {folder}")
    if running:
        report(NOTE, "执行记录", f"{len(running)} 个执行还没有登记结束：{'、'.join(running)}",
               "正在做的任务不用处理；上个会话留下的运行 foreman execution recover 查看")
    if not (unreadable or lost or running):
        report(OK, "执行记录", f"{len(records)} 条" if records else "没有执行记录")


def _web_board(root: Path, report) -> None:
    """Whether the board is up is never a problem: nothing in the workflow needs it."""
    try:
        board = board_status(root)
    except ValueError as error:
        report(NOTE, "看板", str(error))
        return
    if board["listed"]:
        report(OK, "看板", f"正在运行：{board['url']}")
    elif board["running"]:
        report(NOTE, "看板", f"端口 {board['port']} 上有看板在运行，但没有登记这个项目", "foreman web start 把它加进去")
    else:
        report(OK, "看板", "没有运行；想在浏览器里看任务板和进度时运行 foreman web start")


def _dispatch(tasks: list[dict], roles: dict, report) -> None:
    """droid and the model settings matter only to tasks that name a role."""
    waiting = sorted({str(task["role"]) for task in tasks
                      if task.get("role") and task.get("status") not in FINISHED_STATUSES})
    level = PROBLEM if waiting else NOTE
    scope = f"未完成的任务要派给角色 {'、'.join(waiting)}" if waiting else "只影响写了 role 的任务"
    droid = shutil.which("droid")
    if droid:
        report(OK, "droid", droid)
    else:
        report(level, "droid", f"PATH 里没有 droid 命令，不能派发和 preflight（{scope}）",
               "安装 Droid CLI 并确认它在 PATH 中")
    try:
        models = list_byok_models()
    except TeamError as error:
        report(level, "模型配置", f"{error}（{scope}）")
    else:
        if models:
            report(OK, "模型配置", f"{len(models)} 个自己配置的模型")
        else:
            report(level, "模型配置", f"没有自己配置的模型（{scope}）", "在 Droid 里添加自定义模型")
    missing = [role for role in waiting if role not in roles]
    if missing:
        report(PROBLEM, "角色", f"任务用到的角色还没有配置：{'、'.join(missing)}",
               "foreman team set <角色> --model <模型ID> --description <职责>")
    elif waiting:
        report(OK, "角色", f"任务用到的 {len(waiting)} 个角色都已配置；模型服务能否连通用 foreman team check 检查")
