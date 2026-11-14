"""Managed dispatch lifecycle. A worker outcome never implies acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .board import TaskBoard
from .checkpoint import CheckpointError, CheckpointManager
from .config import ExecutionConfig
from .executor import CURRENT_SESSION, TaskExecutor, session_plan
from .history import ExecutionHistory
from .store import _file_lock, _file_scope
from .team import audit_runs


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Committed placeholders such as .env.example belong to a runnable delivery; they are not secrets.
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")


def protected(path: str) -> bool:
    parts = Path(path).parts
    return any(p in {".git", ".factory", ".task-management", ".ssh", ".aws", ".gnupg"}
               or (p.startswith(".env") and not p.endswith(ENV_TEMPLATE_SUFFIXES))
               or p.endswith((".pem", ".key"))
               or p in {"credentials", "credentials.json", "secrets.json"} for p in parts)


def declared_path(root: Path, declared: str) -> Path:
    """Resolve one declared scope; reject paths outside the project, secrets and symlinks."""
    scope = _file_scope(declared)
    path = root / scope
    if not scope or Path(scope).is_absolute() or ".." in Path(scope).parts or protected(scope):
        raise ValueError(f"必须是项目内的明确非敏感路径: {declared}")
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"不允许符号链接: {declared}")
    return path


SKIPPED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
# Bookkeeping the workflow itself rewrites during a run.
OWN_STATE_DIRS = {".git", ".factory", ".task-management"}
LARGE_FILE = 8 * 1024 * 1024


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature(path: bytes, content: bool) -> str:
    try:
        info = os.lstat(path)
    except OSError:
        return "missing"
    if not stat.S_ISREG(info.st_mode):
        return f"{stat.filemode(info.st_mode)[0]}:{info.st_mtime_ns}"
    if not content or info.st_size > LARGE_FILE:
        return f"{info.st_size}:{info.st_mtime_ns}"
    try:
        return _sha256(path)
    except OSError:
        return f"{info.st_size}:{info.st_mtime_ns}"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def _work_tree_prefix(root: Path) -> bytes | None:
    """Where root sits inside its work tree; None when git cannot report on root.

    That covers a folder without a repository, a machine without git, and a project
    an enclosing repository ignores, which would always look clean.
    """
    try:
        prefix = _git(root, "rev-parse", "--show-prefix")
        if prefix.returncode or (prefix.stdout.strip() and _git(root, "check-ignore", "-q", ".").returncode == 0):
            return None
    except OSError:
        return None
    return prefix.stdout.rstrip(b"\n")


def under_git(root: Path) -> bool:
    """Whether the project's changes can be committed and compared with a commit."""
    return _work_tree_prefix(Path(root)) is not None


def worktree_state(root: Path) -> dict | None:
    """Uncommitted paths under root as git status lists them, plus HEAD.

    None when root is not inside a work tree git can report on. Ignored files are
    as invisible here as they are to git status.
    """
    prefix = _work_tree_prefix(root)
    if prefix is None:
        return None
    try:
        status = _git(root, "status", "--porcelain=v1", "-z", "-uall", "--no-renames", "--", ".")
        if status.returncode:
            return None
        head = _git(root, "rev-parse", "-q", "--verify", "HEAD")
    except OSError:
        return None
    skip = len(prefix)
    paths = {}
    for entry in status.stdout.split(b"\0"):
        if len(entry) < 4:
            continue
        raw = entry[3:][skip:].rstrip(b"/")
        relative = raw.decode("utf-8", errors="replace")
        parts = Path(relative).parts
        if (not parts or OWN_STATE_DIRS.intersection(parts) or SKIPPED_DIRS.intersection(parts)
                or parts[0].startswith(("tm-dispatch-", "tm-probe-"))):
            continue
        # Secrets are tracked by size and time only, so no digest of them is stored.
        # The status letters are left out: staging a file is not a change to it.
        paths[relative] = _signature(os.path.join(os.fsencode(root), raw), content=not protected(relative))
    return {"head": head.stdout.decode().strip() or None, "paths": paths}


def _within(path: str, scopes: list[str]) -> bool:
    return any(path == scope or path.startswith(scope + "/") for scope in map(_file_scope, scopes))


def snapshot(root: Path, scopes: list[str]) -> dict[str, str]:
    """Hash declared files, including untracked/ignored files; never follow symlinks."""
    if not scopes:
        raise ValueError("受管派发必须显式声明 files")
    result = {}
    for declared in scopes:
        paths = [declared_path(root, declared)]
        while paths:
            candidate = paths.pop()
            relative = candidate.relative_to(root).as_posix()
            if protected(relative):
                continue
            if candidate.name in SKIPPED_DIRS:
                continue
            if candidate.is_symlink():
                raise ValueError(f"不允许符号链接: {relative}")
            if candidate.is_dir():
                paths.extend(candidate.iterdir())
            elif candidate.is_file():
                result[relative] = _sha256(candidate) + (":x" if candidate.stat().st_mode & 0o111 else "")
    return result


def requirements(task: dict) -> list[dict]:
    checks = task.get("acceptance")
    if not isinstance(checks, list) or not checks:
        raise ValueError("缺少结构化 acceptance：每项须有 id、scenario、expected、method")
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or any(
            not isinstance(check.get(key), str) or not check[key].strip()
            for key in ("id", "scenario", "expected", "method")
        ):
            raise ValueError("验收条件字段不完整")
        if check["id"] in seen or check["method"] not in {"command", "browser", "manual"}:
            raise ValueError("验收 ID 重复或 method 无效")
        seen.add(check["id"])
        if check["method"] == "command" and not check.get("command"):
            raise ValueError("command 验收条件需要 command")
    return checks


def evidence_template(task: dict, undeclared: list[str] | None = None, execution_id: str | None = None) -> dict:
    """Skeleton for execution accept. Verdicts and evidence are blank, so it is refused until filled in.

    execution_id names the run the evidence is about; accept refuses it for any other run.
    """
    checks = []
    for check in requirements(task):
        item = {"id": check["id"], "status": "", "evidence": "", "scenario": check["scenario"],
                "expected": check["expected"], "method": check["method"]}
        if check.get("command"):
            item["command"] = check["command"]
        checks.append(item)
    template = {"execution_id": execution_id} if execution_id else {}
    template.update(inspection="", checks=checks)
    if undeclared:
        template["undeclared"] = ""
    return template


# File times are kept to the second, or to two seconds, on some filesystems.
EVIDENCE_TIME_SLACK = 2.0


def process_started(pid: int) -> str | None:
    """When the process with this PID started, as ps prints it; None when there is no such process.

    A PID is handed out again after its process exits, so the start time is what identifies a process.
    """
    try:
        listed = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True,
                                check=False, env={**os.environ, "LC_ALL": "C"})
    except OSError:
        return None
    started = " ".join(listed.stdout.split())
    return started if listed.returncode == 0 and started else None


def _content_digest(accepted: dict) -> str:
    """One digest for everything acceptance pinned: it stands in for the commit in a project without git."""
    pinned = {"files": accepted["snapshot"], "runtime_dependencies": accepted["dependency_snapshot"]}
    return hashlib.sha256(json.dumps(pinned, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _path_list(task: dict, field: str, purpose: str) -> list[str]:
    paths = task.get(field)
    if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p.strip() for p in paths):
        raise ValueError(f"受管任务需声明 {field}（非空的路径列表），{purpose}")
    return paths


def task_files(task: dict) -> list[str]:
    return _path_list(task, "files", "列出会修改的文件或目录")


def runtime_dependencies(task: dict) -> list[str]:
    return _path_list(task, "runtime_dependencies", "包含实际运行所需代码和配置模板")


DISPATCH_OUTCOMES = {"returned", "permission_rejected", "failed", "interrupted"}
DIRECT_OUTCOMES = {"completed", "failed", "interrupted"}


def is_direct(record) -> bool:
    """The current session did the work itself; records written before modes existed are dispatches."""
    return record.details.get("mode") == "direct"


def model_verified(record) -> bool:
    return is_direct(record) or record.details["audit"]["status"] == "passed"


def changed(before: dict[str, str], after: dict[str, str]) -> str:
    paths = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
    return "、".join(paths[:5]) + (f" 等 {len(paths)} 个路径" if len(paths) > 5 else "")


class Workflow:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.board = TaskBoard.load(self.root)
        self.history = ExecutionHistory(self.root)
        self.lock = self.root / ".task-management" / "workflow"
        self.checkpoint_set_aside: Path | None = None

    def _task(self, task_id: str) -> dict:
        """The task, or the refusal for an ID that is not on the board.

        begin and integrate ask before taking the lock, so a mistyped ID does not create .task-management/.
        """
        task = self.board.get_task(task_id)
        if not task:
            raise ValueError(f"任务 {task_id} 不存在")
        return task

    def current_record(self, task: dict):
        """The run the board currently points this task at; None before its first begin."""
        return self.history._load_record(task["execution_id"]) if task.get("execution_id") else None

    def resolve_execution_id(self, value: str) -> str:
        """Accept a task ID wherever an execution ID is expected: it stands for the task's current run."""
        if self.history._load_record(value):
            return value
        task = self.board.get_task(value)
        if not task:
            raise ValueError(f"找不到执行记录或任务 {value}")
        if not task.get("execution_id"):
            raise ValueError(f"任务 {task['id']} 还没有执行记录；先运行 foreman execution begin {task['id']}")
        return task["execution_id"]

    def _record(self, execution_id):
        record = self.history._load_record(execution_id)
        if not record:
            raise ValueError(f"找不到受管执行记录 {execution_id}：{self.history.history_dir} 下没有这个文件，"
                             "它可能被删除，或没有随项目一起拷贝；恢复这个文件后重试")
        if not record.details.get("managed"):
            raise ValueError(f"找不到受管执行记录：{execution_id} 不是 execution begin 或 run 登记的记录")
        return record

    def _latest(self, record):
        task = self.board.get_task(record.task_id)
        if not task or task.get("execution_id") != record.execution_id:
            raise ValueError("该执行已被后续派发替代，不允许修改当前任务")
        return task

    def _undeclared(self, record) -> dict:
        """Paths outside this run's files that changed while it ran. Git cannot say who changed them."""
        before, after = record.details.get("worktree"), worktree_state(self.root)
        if before is None or after is None:
            return {"checked": False, "paths": [], "head_moved": False}
        scopes = list(record.details["files"])
        for other in self.board.get_all_tasks():
            if other.get("id") == record.task_id or not other.get("execution_id"):
                continue
            try:
                peer = self.history._load_record(other["execution_id"])
            except ValueError:
                continue
            # A task that ran alongside this one owns the changes inside its own files.
            if peer and (peer.status == "running" or (peer.recorded_at or "") > record.start_time):
                scopes.extend(peer.details.get("files", []))
        # The main agent keeps specs and acceptance evidence beside the board while runs are in flight.
        workspace = self.board.task_file.parent.relative_to(self.root).as_posix() + "/"
        def current(path: str) -> str:
            # No longer listed means it now matches HEAD. Committing a file does not change it,
            # so compare what is on disk rather than whether git still lists it.
            if path in after["paths"]:
                return after["paths"][path]
            return _signature(os.path.join(os.fsencode(self.root), os.fsencode(path)), content=not protected(path))

        moved = {p for p in before["paths"].keys() | after["paths"].keys()
                 if before["paths"].get(p) != current(p)}
        # Strays left by the run this one retries are still unexplained while uncommitted.
        moved.update(p for p in record.details.get("carried_undeclared", []) if p in after["paths"])
        return {"checked": True, "head_moved": before["head"] != after["head"],
                "paths": sorted(p for p in moved if not _within(p, scopes) and not p.startswith(workspace))}

    def sync(self, event: bool = False) -> None:
        """Rewrite the checkpoint's progress from the board.

        event says an execution step just happened: what checkpoint save wrote before it
        may no longer be true, and checkpoint check marks it. Repairing the checkpoint is not an event.
        An unreadable checkpoint is moved aside, not overwritten; checkpoint_set_aside names where.
        """
        checkpoint = CheckpointManager(self.root)
        try:
            previous = checkpoint.load() or {}
        except CheckpointError:
            # Every execution command ends here; failing now would report an error
            # for a step whose record and board update have already been saved.
            self.checkpoint_set_aside, previous = checkpoint.set_aside(), {}
        data = previous.get("data", {})
        tasks = self.board.get_all_tasks()
        completed = sum(t.get("status") == "DONE" and bool(t.get("integration")) for t in tasks)
        active = [t["id"] for t in tasks if t.get("status") == "IN_PROGRESS"]
        progress = dict(total_tasks=len(tasks), completed_tasks=completed, active_tasks=active,
                        current_task=active[0] if len(active) == 1 else None,
                        task_file="planning/tasks.md")
        data.update(progress)
        written = previous.get("written_at")
        # These now come from the board, whoever wrote them last.
        written = {key: stamp for key, stamp in written.items() if key not in progress} if isinstance(written, dict) else {}
        checkpoint.write("completed" if tasks and completed == len(tasks) else "developing", data, written,
                         now() if event else previous.get("last_event_at"))

    def begin(self, task_id: str) -> dict:
        self._task(task_id)
        with _file_lock(self.lock):
            plan = TaskExecutor(self.root).plan_execution(task_id)
            task = self.board.get_task(task_id)
            direct = plan["mode"] == "direct"
            carried = []
            if task.get("execution_id"):
                previous = self._record(task["execution_id"])
                if previous.status == "running":
                    raise ValueError(
                        f"任务 {task['id']} 已经登记开始，还没有登记结束：运行 foreman show {task['id']} "
                        "查看该用哪条 finish 命令；想重做也要先 finish，再检查并明确 retry"
                    )
                if previous.details.get("recovery", {}).get("decision") != "retry":
                    raise ValueError(
                        f"任务 {task['id']} 的上次执行还没有了结，不能重新开始：运行 foreman show {task['id']} "
                        "查看下一步（验收、集成，或检查后明确 retry 再重做）；不能仅改为 PENDING 后重派"
                    )
                carried = (previous.details.get("undeclared") or {}).get("paths", [])
            if not direct and not plan["model"]:
                raise ValueError("受管派发需要用户选定模型的 role")
            checks = requirements(task)
            # A string here would be split into characters and snapshot the whole project.
            task_files(task)
            dependencies = runtime_dependencies(task)
            config = ExecutionConfig(self.root)
            running = [str(t.get("id")) for t in self.board.get_all_tasks() if t.get("status") == "IN_PROGRESS"]
            if len(running) >= config.get_max_parallel():
                raise ValueError(
                    f"已达到并发上限 {config.get_max_parallel()}：任务 {'、'.join(running)} 正在进行。"
                    "等它们登记结束，或用 foreman config set parallel.max_parallel=<数字> 调高上限"
                )
            selection = self.board.select_batch(config.get_roles(), config.get_max_parallel())
            if task["id"] not in {t["id"] for t in selection["batch"]}:
                reason = next((item["reason"] for item in selection["skipped"] if item["id"] == task["id"]), None)
                # Only tasks in a ready status are considered at all, so no reason means the status.
                raise ValueError(f"任务尚不可开始：{reason}" if reason else
                                 f"任务尚不可开始：状态是 {task.get('status', 'PENDING')}，只有待开始（PENDING）的任务可以开始")
            before = snapshot(self.root, plan["files"])
            # Reject unusable dependency paths now, not after the worker has finished.
            snapshot(self.root, dependencies)
            execution_id = self.history.record_start(
                task["id"], CURRENT_SESSION if direct else plan["droid"], plan["complexity"], plan["model"],
                details={"managed": True, "mode": plan["mode"], "files": plan["files"], "before": before,
                         "worktree": worktree_state(self.root), "carried_undeclared": carried,
                         "requirements": checks, "dispatch_outcome": "running",
                         "acceptance": {"status": "pending"},
                         # No sub-agent runs in direct mode, so there is no model to verify.
                         "audit": {"status": "not_applicable" if direct else "pending"}},
            )
            self.board.update_task(task["id"], {"status": "IN_PROGRESS", "execution_id": execution_id})
            self.sync(event=True)
            plan["execution_id"] = execution_id
            if direct:
                session_plan(plan)
                plan["instruction"] = (
                    "由当前会话直接实现，只修改 files 列出的路径。"
                    f"做完后运行 foreman execution finish {execution_id} --outcome completed，"
                    "再 execution inspect、逐项验收并 execution accept。"
                )
                return plan
            plan["task_args"]["description"] = f"[tm:{execution_id}] {plan['task_title']}"
            # Enumerating the tool object returns nothing in script mode, which a
            # worker once read as "no tools" and stopped without attempting the task.
            plan["task_args"]["prompt"] += (
                "\n\n直接调用完成任务所需的工具。不要通过枚举工具对象判断是否可用："
                "脚本模式下枚举结果为空不代表没有工具。"
                "\n某次调用被拒绝时，报告工具名和原始错误，不要据此推断其他工具也不可用。"
                "\nExecute 需要 command、riskLevel、summary；不要传 cwd，"
                "在命令中显式 cd 到项目绝对路径。"
                "\nriskLevel 如实填写 low 或 medium。标为 high 的命令会被拒绝并终止整个派发；"
                "确实需要这类操作时停止并报告。"
                "\n沙箱内不能联网、不能使用 git，也可能读不到装在用户目录下的工具（例如 pytest）。"
                "验证命令因此无法运行时，如实报告哪一条没有运行及原始错误，不要尝试安装或绕过。"
                "\n若权限拒绝或中断，报告已经写入的文件和未完成事项。"
                "不要把派发失败解释为没有文件改动。主 Agent 将独立验收。"
            )
            return plan

    def finish(self, execution_id: str, outcome: str, ended_at: str | None = None, transport: dict | None = None):
        if outcome not in DISPATCH_OUTCOMES | DIRECT_OUTCOMES:
            raise ValueError("未知的执行结果")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            if is_direct(record) and outcome not in DIRECT_OUTCOMES:
                raise ValueError("当前会话直接执行的任务用 completed（做完）、failed（没做完）或 interrupted")
            if not is_direct(record) and outcome not in DISPATCH_OUTCOMES:
                raise ValueError("completed 只用于当前会话直接执行的任务；派发结果用 returned、"
                                 "permission_rejected、failed 或 interrupted")
            first = record.status == "running"
            if first:
                # The baseline is only needed for this comparison; dropping it keeps records small.
                details = {"dispatch_outcome": outcome, "inspection_required": True,
                           "undeclared": self._undeclared(record), "worktree": None}
                if transport:
                    details["transport"] = transport
                # One write carries status and outcome, so an interruption cannot leave a
                # finished record that still claims to be running. An interrupted run may
                # have stopped long before bookkeeping, hence the unknown end time.
                self.history.record_completion(
                    execution_id, "success" if outcome in {"returned", "completed"} else "failed",
                    ended_at=ended_at, time_unknown=outcome == "interrupted" and ended_at is None,
                    details=details,
                )
                record = self._record(execution_id)
            elif record.details["dispatch_outcome"] != outcome:
                raise ValueError(f"执行结果已登记为 {record.details['dispatch_outcome']}，不能改成 {outcome}")
            # Repeating finish repairs a board update lost after the record was saved.
            # Keep file ownership until independent inspection and acceptance.
            if first or task["status"] == "IN_PROGRESS":
                self.board.update_task_status(task["id"], "AWAITING_REVIEW")
            self.sync(event=first)
            return asdict(record)

    def inspect(self, execution_id: str) -> dict:
        record = self._record(execution_id)
        current = snapshot(self.root, record.details["files"])
        before = record.details["before"]
        direct = is_direct(record)
        span = "执行期间" if direct else "派发期间"
        report = {
            "execution_id": execution_id, "mode": "direct" if direct else "dispatch",
            "dispatch_outcome": record.details["dispatch_outcome"],
            "added": sorted(current.keys() - before.keys()),
            "deleted": sorted(before.keys() - current.keys()),
            "modified": sorted(p for p in before.keys() & current.keys() if before[p] != current[p]),
            "baseline_files": sorted(before), "acceptance": record.details["acceptance"],
            "instruction": "差异只说明文件变化，不证明是谁修改或是否完成。检查 diff 和新增文件后再决定。",
        }
        if record.details.get("processes"):
            report["processes"] = [{"pid": item["pid"], "label": item["label"],
                                    "running": process_started(item["pid"]) == item["started"]}
                                   for item in record.details["processes"]]
        if record.status == "running":
            # Nothing is concluded before finish, but the stray paths are already listed:
            # a session taking over this run has to see them before it adds changes of its own.
            report["undeclared"] = self._undeclared(record)
            report["instruction"] += "还没有登记结束：undeclared 是当前的快照，finish 时会重新记录，notices 也在那之后才有。"
            return report
        undeclared = record.details.get("undeclared") or {"checked": False, "paths": [], "head_moved": False}
        notices = []
        if not (report["added"] or report["deleted"] or report["modified"]):
            notices.append("声明的 files 与开始前相比没有任何变化：成果可能写到了别处，或任务的 files 写错了。不要验收。"
                           if direct else
                           "声明的 files 与派发前相比没有任何变化：子 Agent 可能没有动手，或把成果写到了别处。"
                           "不要仅凭它的报告验收。")
        if undeclared["paths"]:
            notices.append(f"{span}有 {len(undeclared['paths'])} 个声明范围外的路径发生变化（见 undeclared.paths）。"
                           "逐个查看，并在验收证据的 undeclared 字段写明来源和处理结论。")
        if undeclared["head_moved"]:
            notices.append(f"{span} HEAD 发生变化（有新提交或切换了分支）。"
                           + ("" if direct else "沙箱内的子 Agent 不能提交，确认这是你或用户做的；")
                           + "内容因此变化的文件已列在 undeclared.paths。")
        if not undeclared["checked"]:
            notices.append("本次执行没有检查声明范围外的改动（不是 git 仓库、git 不可用或旧记录），需要人工核对。")
        report.update(undeclared=undeclared, notices=notices)
        return report

    def audit(self, execution_id: str, sessions_dir: Path | None = None):
        with _file_lock(self.lock):
            record = self._record(execution_id)
            self._latest(record)
            if is_direct(record):
                return record.details["audit"]
            records = audit_runs(self.root, sessions_dir=sessions_dir, limit=10000, execution_id=execution_id)
            # Compare to the model pinned at dispatch, not a subsequently edited role.
            for item in records:
                item["expected"] = record.model
                item["ok"] = item["actual"] == record.model
            result = {"status": "passed" if len(records) == 1 and records[0]["ok"] else "unverified",
                      "records": records, "recorded_at": now()}
            record.details["audit"] = result
            self.history._save_record(execution_id, record)
            return result

    def accept(self, execution_id: str, evidence: dict, written_at: float | None = None):
        """Store main-agent evidence independently of the worker result.

        written_at is when the evidence file was last modified, for evidence that came from a file.
        """
        if not isinstance(evidence, dict):
            raise ValueError("验收证据格式错误：应是含 inspection 和 checks 的 JSON 对象；"
                             "用 foreman acceptance <任务ID> --template 生成框架")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            direct = is_direct(record)
            if record.status == "running":
                raise ValueError("先运行 foreman execution finish <任务ID> --outcome completed 登记做完" if direct else
                                 "先登记派发结束；中断时用 interrupted，未知结束时间保持为空")
            if task["status"] not in {"AWAITING_REVIEW", "AWAITING_INTEGRATION"}:
                raise ValueError("任务已集成或已决定重新派发，不能用旧记录重新验收")
            # A file filled in for an earlier run of this task is still on disk after a retry.
            regenerate = (f"用 foreman acceptance {task['id']} --template --force 重新生成框架，"
                          "按这次执行的实际结果逐项重验后填写")
            claimed = evidence.get("execution_id")
            if claimed is not None and claimed != record.execution_id:
                raise ValueError(f"验收证据是为执行 {claimed} 写的，这次执行是 {record.execution_id}；{regenerate}")
            finished = datetime.fromisoformat(record.recorded_at).timestamp() if record.recorded_at else None
            if written_at is not None and finished is not None and written_at < finished - EVIDENCE_TIME_SLACK:
                raise ValueError("验收证据文件最后修改于这次执行登记结束之前，不是对这次执行的验收："
                                 "证据要在 finish 之后逐项运行或观察取得；" + regenerate)
            if not model_verified(record):
                raise ValueError("实际模型尚未核对通过，不能验收")
            checks = requirements(task)
            if checks != record.details["requirements"]:
                raise ValueError("派发后验收条件已变更，需要新一轮执行记录")
            dependencies = runtime_dependencies(task)
            results = evidence.get("checks", [])
            if not isinstance(results, list) or not all(isinstance(r, dict) and isinstance(r.get("id"), str)
                                                        for r in results):
                raise ValueError("验收证据格式错误：checks 应是列表，每项是含 id、status、evidence 的 JSON 对象")
            if len(results) != len(checks) or {r["id"] for r in results} != {c["id"] for c in checks}:
                raise ValueError("必须提供全部验收条件的结果，不能遗漏或重复；应有的 id: "
                                 + "、".join(c["id"] for c in checks))
            if not isinstance(evidence.get("inspection"), str) or not evidence["inspection"].strip():
                raise ValueError("必须记录实际文件审查结论：在 inspection 字段写明看过哪些文件、结论是什么")
            unproven = [r["id"] for r in results if r.get("status") != "passed"
                        or not isinstance(r.get("evidence"), str) or not r["evidence"].strip()]
            if unproven:
                raise ValueError(f"验收未全部通过或缺少证据: {'、'.join(unproven)}。"
                                 "每项的 status 须为 passed，evidence 写明实际运行或观察到的结果")
            undeclared = record.details.get("undeclared") or {}
            explained = evidence.get("undeclared")
            if undeclared.get("paths") and not (isinstance(explained, str) and explained.strip()):
                raise ValueError(("执行期间" if direct else "派发期间") + "有声明范围外的改动；先 execution inspect 查看，"
                                 "再在验收证据的 undeclared 字段写明来源和处理结论")
            if record.details["acceptance"]["status"] != "pending":
                record.details.setdefault("acceptance_history", []).append(record.details["acceptance"])
            record.details["acceptance"] = {
                "status": "passed", "recorded_at": now(), "checks": results,
                "inspection": evidence["inspection"], "undeclared": explained,
                # The session that wrote the change also judged it; a reader should know that.
                "self_review": direct,
                "snapshot": snapshot(self.root, record.details["files"]),
                # What was observed running includes these paths, so they are pinned too.
                "runtime_dependencies": dependencies,
                "dependency_snapshot": snapshot(self.root, dependencies),
            }
            record.details["inspection_required"] = False
            self.history._save_record(execution_id, record)
            self.board.update_task_status(task["id"], "AWAITING_INTEGRATION", reset_retries=True)
            self.sync(event=True)
            return self.board.get_task(task["id"])

    def retry(self, execution_id: str, reason: str, block: bool = False):
        if not reason.strip():
            raise ValueError("必须说明文件检查结果及续做范围")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            if record.status == "running" or task["status"] == "DONE":
                raise ValueError("先用 execution finish 登记结束；已集成任务不能从旧记录重试")
            if task["status"] == "BLOCKED" and not block:
                raise ValueError("任务已 BLOCKED；用户处理后用 execution unblock 恢复，retry 只会累加失败次数")
            inspection = self.inspect(execution_id)
            record.details["recovery"] = {"recorded_at": now(), "reason": reason,
                                          "inspection": inspection, "decision": "block" if block else "retry"}
            if record.details["acceptance"]["status"] == "passed":
                record.details["acceptance"]["status"] = "invalidated"
            self.history._save_record(execution_id, record)
            self.board.record_failure(task["id"], ExecutionConfig(self.root).get_max_retries(), block, reason)
            self.sync(event=True)

    def pause(self, execution_id: str, reason: str) -> dict:
        """Put a run the user stopped back to PENDING. Being told to stop is not a failed attempt."""
        if not reason.strip():
            raise ValueError("必须说明用户为什么叫停，以及已经做完的部分")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            if record.status == "running":
                raise ValueError(f"先运行 foreman execution finish {task['id']} --outcome interrupted "
                                 "登记这次执行被叫停，再 pause")
            outcome = record.details["dispatch_outcome"]
            if outcome != "interrupted" or (record.details.get("transport") or {}).get("timed_out"):
                raise ValueError(f"这次执行登记的结果是 {'超时终止' if outcome == 'interrupted' else outcome}，"
                                 "不是用户叫停：pause 只用于用户叫停的执行；没做完或失败用 execution retry")
            if task["status"] != "AWAITING_REVIEW":
                raise ValueError(f"只有登记结束、还没有验收的任务可以暂停（现在是 {task['status']}）；"
                                 f"运行 foreman show {task['id']} 查看下一步")
            record.details["recovery"] = {"recorded_at": now(), "reason": reason, "inspection": self.inspect(execution_id),
                                          "decision": "retry", "paused": True}
            self.history._save_record(execution_id, record)
            # failed_attempts is left as it is: only retry counts towards the limit.
            task = self.board.update_task(task["id"], {"status": "PENDING",
                                                       "last_failure": f"用户叫停（不计失败次数）：{reason}"})
            self.sync(event=True)
            return task

    def track(self, execution_id: str, pid: int, label: str) -> dict:
        """Note a process started for this run that outlives the command that started it."""
        if not label.strip():
            raise ValueError("必须说明这个进程是什么，例如“dev server，端口 5173”")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            if task["status"] == "DONE":
                raise ValueError("任务已集成，不再登记进程")
            started = process_started(pid) if pid > 0 else None
            if not started:
                raise ValueError(f"没有 PID 为 {pid} 的进程：登记的是还在运行的进程")
            entry = {"pid": pid, "label": label.strip(), "started": started, "recorded_at": now()}
            kept = [item for item in record.details.get("processes", [])
                    if (item["pid"], item["started"]) != (pid, started)]
            record.details["processes"] = [*kept, entry]
            self.history._save_record(execution_id, record)
            return entry

    def running_processes(self, execution_id: str) -> list[dict]:
        """The processes noted for this run that are still alive."""
        record = self._record(execution_id)
        return [item for item in record.details.get("processes", []) if process_started(item["pid"]) == item["started"]]

    def unblock(self, execution_id: str, reason: str):
        """Resume a BLOCKED task on the user's decision without counting another failure."""
        if not reason.strip():
            raise ValueError("必须说明用户的处理结果")
        with _file_lock(self.lock):
            record = self._record(execution_id)
            task = self._latest(record)
            if record.status == "running" or task["status"] != "BLOCKED":
                raise ValueError("只有已结束派发且处于 BLOCKED 的受管任务可以解除阻塞")
            if record.details.get("recovery"):
                record.details.setdefault("recovery_history", []).append(record.details["recovery"])
            record.details["recovery"] = {"recorded_at": now(), "reason": reason,
                                          "decision": "retry", "unblocked": True}
            self.history._save_record(execution_id, record)
            note = "\n".join(filter(None, [task.get("last_failure"), f"解除阻塞：{reason}"]))
            self.board.update_task(task["id"], {"status": "PENDING", "failed_attempts": 0, "last_failure": note})
            self.sync(event=True)

    def integration_ready(self, task_id: str, commit: str | None = None, repo: Path | None = None):
        task = self._task(task_id)
        if not task.get("execution_id"):
            return  # Legacy tasks retain their existing integration contract.
        if task["status"] != "AWAITING_INTEGRATION":
            raise ValueError(f"任务尚未处于待集成状态（现在是 {task['status']}）；"
                             f"运行 foreman show {task['id']} 查看下一步")
        record = self._record(task["execution_id"])
        accepted = record.details["acceptance"]
        if accepted["status"] != "passed" or not model_verified(record):
            raise ValueError("受管任务尚未通过独立验收及模型审计")
        if requirements(task) != record.details["requirements"]:
            raise ValueError("验收条件已变更")
        current = snapshot(self.root, record.details["files"])
        if current != accepted["snapshot"]:
            raise ValueError("验收后文件已变化，需要重新验收: " + changed(accepted["snapshot"], current))
        dependencies = runtime_dependencies(task)
        if dependencies != accepted.get("runtime_dependencies") or "dependency_snapshot" not in accepted:
            raise ValueError("运行依赖声明在验收后已变更或未随验收记录，需要重新验收")
        current = snapshot(self.root, dependencies)
        if current != accepted["dependency_snapshot"]:
            raise ValueError("验收后运行依赖已变化，需要重新验收: "
                             + changed(accepted["dependency_snapshot"], current))
        if commit is not None:
            if repo and repo.resolve() != self.root:
                raise ValueError("受管任务需要在当前已验收仓库集成；跨仓库须单独验收")
            report = delivery_check(self.root, commit, record.details["files"] + dependencies)
            if not report["ok"]:
                raise ValueError("提交未包含全部已验收文件或运行依赖；先运行 foreman delivery --commit <SHA> --paths <路径...> 查看缺失路径")

    def integrate(self, task_id: str, commit: str | None, repo: Path, note: str = "") -> dict:
        """Check, record the integration and mark DONE under one lock so nothing interleaves.

        commit is None for a project without git: there is no commit to check, so the
        digest of what acceptance pinned is recorded in its place.
        """
        self._task(task_id)
        if commit is None:
            if not note.strip():
                raise ValueError("--no-git 需要 --note：写明成果保存在哪里、怎么留存（例如备份的位置）")
            if under_git(self.root):
                raise ValueError(f"{self.root} 在 git 仓库里：提交任务的改动后用 foreman integrate {task_id} "
                                 "--commit <提交 SHA>；--no-git 只用于没有 git 的项目")
        with _file_lock(self.lock):
            task = self.board.get_task(task_id)
            if task and task.get("execution_id") and task["status"] == "DONE":
                done = (task.get("integration") or {}).get("commit")
                if done != commit:
                    raise ValueError(f"任务已集成（提交 {str(done)[:12]}），不能改记为其他提交" if done else
                                     "任务已按内容快照集成（没有提交），不能改记为提交")
                self.sync()
                return task
            self.integration_ready(task_id, commit, repo)
            digest = None
            # Record first: if the board update is lost, repeating integrate still passes
            # the checks above, whereas a DONE task could never be recorded afterwards.
            if task.get("execution_id"):
                record = self._record(task["execution_id"])
                record.details["integration"] = {"commit": commit, "recorded_at": now()}
                if commit is None:
                    digest = _content_digest(record.details["acceptance"])
                    record.details["integration"].update(mode="no-git", digest=digest)
                self.history._save_record(record.execution_id, record)
            task = self.board.confirm_integration(task_id, commit, str(repo), note, digest)
            self.sync(event=True)
            return task


def resolve_commit(repo: Path, commit: str) -> str:
    """Full SHA of a commit in repo. When it cannot be resolved, the error says which of the usual causes it is."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)

    try:
        resolved = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    except OSError as error:
        raise ValueError(f"无法运行 git（{error}）；确认 git 已安装并在 PATH 中") from error
    if resolved.returncode == 0:
        return resolved.stdout.strip()
    if git("rev-parse", "--git-dir").returncode:
        raise ValueError(f"{repo} 不是 git 仓库，无法核对提交 {commit}")
    if git("rev-parse", "--verify", "--quiet", "HEAD").returncode:
        raise ValueError(f"{repo} 还没有任何提交；先提交任务的改动，再用那个提交运行这条命令")
    raise ValueError(f"在 {repo} 中找不到提交 {commit}")


def delivery_check(root: Path, commit: str, paths: list[str]) -> dict:
    """Check explicit runtime dependencies against a commit without changing the index."""
    root = root.resolve()
    sha = resolve_commit(root, commit)
    if not paths:
        raise ValueError("交付检查需要显式声明所有运行依赖路径")
    current = snapshot(root, paths)
    issues = []
    listing = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "-z", sha],
                             capture_output=True, check=True)
    stored_paths = {}
    scopes = [_file_scope(p) for p in paths]
    for entry in listing.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if protected(path) or not any(path == s or path.startswith(s + "/") for s in scopes):
            continue
        mode, kind, blob = metadata.decode().split()
        if kind != "blob" or mode == "120000":
            issues.append({"path": path, "reason": "unsupported_link"})
            continue
        stored = subprocess.run(["git", "-C", str(root), "cat-file", "blob", blob],
                                capture_output=True, check=True)
        stored_paths[path] = hashlib.sha256(stored.stdout).hexdigest() + (":x" if mode == "100755" else "")
    for path in sorted(current.keys() | stored_paths.keys()):
        if path not in stored_paths:
            issues.append({"path": path, "reason": "missing_from_commit"})
        elif path not in current:
            issues.append({"path": path, "reason": "deleted_only_in_worktree"})
        elif current[path] != stored_paths[path]:
            issues.append({"path": path, "reason": "differs_from_commit"})
    for path in paths:
        if not (root / _file_scope(path)).exists():
            issues.append({"path": path, "reason": "missing_from_worktree"})
    return {"commit": sha, "paths": paths, "ok": not issues, "issues": issues,
            "scope": "仅检查显式依赖路径的内容；还需在干净检出中运行启动和验收命令"}
