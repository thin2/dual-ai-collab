#!/usr/bin/env python3
"""task_manager.py - 统一任务管理核心（替代 7 个 Shell 脚本的逻辑层）

子命令:
  init          初始化工作环境
  update        更新任务状态
  select        选择下一个可执行任务
  checkpoint-write  写入 checkpoint
  checkpoint-check  检查 checkpoint
  detect        检测进程卡死
  summary       统计进度
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# 区域 1：基础设施
# ═══════════════════════════════════════════════════════════════════════════════


class AtomicWriter:
    """先写临时文件 + os.fsync + os.rename，保证写入原子性。"""

    @staticmethod
    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp, str(path))
        except BaseException:
            os.unlink(tmp)
            raise

class FileLock:
    """fcntl.flock 排他锁，用作 context manager。"""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self.lock_path, "w")
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        self._fd.close()
        return False


class MarkdownParser:
    """状态机逐行解析 codex-tasks.md → 结构化任务列表。"""

    @staticmethod
    def parse(text: str) -> list[dict]:
        tasks = []
        current = None
        desc_lines = []
        in_desc = False

        for line in text.splitlines():
            m = re.match(r"^## 任务 #(\d+):\s*(.*)", line)
            if m:
                if current is not None:
                    current["description"] = "\n".join(desc_lines).strip()
                    tasks.append(current)
                current = {
                    "id": m.group(1),
                    "title": m.group(2).strip(),
                    "priority": "P9",
                    "status": "",
                    "status_explicit": False,
                    "assigned_to": "",
                    "dependencies": "无",
                    "execution_level": "",
                    "stall_threshold_minutes": "",
                    "description": "",
                }
                desc_lines = []
                in_desc = False
                continue

            if current is None:
                continue

            if line.strip() == "---":
                current["description"] = "\n".join(desc_lines).strip()
                tasks.append(current)
                current = None
                desc_lines = []
                in_desc = False
                continue

            # 解析字段
            pm = re.match(r"\*\*优先级\*\*:\s*(P\d)", line)
            if pm:
                current["priority"] = pm.group(1)
                continue
            sm = re.match(r"\*\*状态\*\*:\s*(\S+)", line)
            if sm:
                current["status"] = sm.group(1)
                current["status_explicit"] = True
                continue
            am = re.match(r"\*\*分配给\*\*:\s*(.*)", line)
            if am:
                current["assigned_to"] = am.group(1).strip()
                continue
            dm = re.match(r"\*\*依赖任务\*\*:\s*(.*)", line)
            if dm:
                current["dependencies"] = dm.group(1).strip()
                continue
            em = re.match(r"\*\*执行级别\*\*:\s*(\S+)", line)
            if em:
                current["execution_level"] = em.group(1)
                continue
            tm = re.match(r"\*\*卡死阈值\*\*:\s*(\d+)", line)
            if tm:
                current["stall_threshold_minutes"] = tm.group(1)
                continue

            # 描述区域
            if re.match(r"^### 任务描述", line):
                in_desc = True
                continue
            if in_desc:
                desc_lines.append(line)

        # 文件末尾没有 --- 的情况
        if current is not None:
            current["description"] = "\n".join(desc_lines).strip()
            tasks.append(current)

        return tasks


class MarkdownRenderer:
    """结构化数据 → Markdown，保持现有格式。"""

    @staticmethod
    def render(tasks: list[dict], header: str = "") -> str:
        lines = []
        if header:
            lines.append(header)
            lines.append("")
        for task in tasks:
            lines.append(f"## 任务 #{task['id']}: {task['title']}")
            lines.append("")
            if task.get("priority") and task["priority"] != "P9":
                lines.append(f"**优先级**: {task['priority']}")
            lines.append(f"**状态**: {task['status']}")
            if task.get("assigned_to"):
                lines.append(f"**分配给**: {task['assigned_to']}")
            if task.get("dependencies"):
                lines.append(f"**依赖任务**: {task['dependencies']}")
            if task.get("execution_level"):
                lines.append(f"**执行级别**: {task['execution_level']}")
            if task.get("stall_threshold_minutes"):
                lines.append(f"**卡死阈值**: {task['stall_threshold_minutes']}m")
            if task.get("description"):
                lines.append("")
                lines.append("### 任务描述")
                lines.append(task["description"])
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)


class CheckpointStore:
    """state.json 读写层（整合原子写入+文件锁）。"""

    ALLOWED_FIELDS = {
        "spec_file", "task_file", "current_task",
        "total_tasks", "completed_tasks", "fix_round",
    }
    VALID_PHASES = {
        "interview", "spec_generated", "tasks_created",
        "user_approved", "developing", "auditing", "fixing",
    }
    CHECKPOINT_DIR = Path(".dual-ai-collab/checkpoints")
    STATE_FILE = CHECKPOINT_DIR / "state.json"
    LOCK_FILE = CHECKPOINT_DIR / "state.json.lock"

    @classmethod
    def read(cls) -> dict:
        if not cls.STATE_FILE.exists():
            return {}
        try:
            with open(cls.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            backup = cls.STATE_FILE.with_suffix(cls.STATE_FILE.suffix + ".corrupted")
            shutil.copy2(cls.STATE_FILE, backup)
            print(
                f"WARNING: 现有 checkpoint 非法，已备份到 {backup.name}，将重新生成。",
                file=sys.stderr,
            )
        return {}

    @classmethod
    def write(cls, phase: str, extra_args: list[str]) -> str:
        if phase not in cls.VALID_PHASES:
            print(f"ERROR: 无效的 phase 值: {phase}", file=sys.stderr)
            print(f"允许: {'|'.join(sorted(cls.VALID_PHASES))}", file=sys.stderr)
            sys.exit(1)

        cls.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with FileLock(cls.LOCK_FILE):
            data = cls.read()

            for item in extra_args:
                if "=" not in item:
                    print(f"ERROR: 非法参数 '{item}'，必须使用 key=value 格式。", file=sys.stderr)
                    sys.exit(1)
                key, value = item.split("=", 1)
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    print(f"ERROR: 非法字段名 '{key}'。", file=sys.stderr)
                    sys.exit(1)
                if key not in cls.ALLOWED_FIELDS:
                    print(
                        f"WARNING: 未知字段 '{key}' 被忽略（允许: {', '.join(sorted(cls.ALLOWED_FIELDS))}）",
                        file=sys.stderr,
                    )
                    continue
                data[key] = value

            data["phase"] = phase
            data["updated_at"] = updated_at

            ordered = {"phase": data["phase"], "updated_at": data["updated_at"]}
            for key in ("spec_file", "task_file", "current_task", "total_tasks", "completed_tasks", "fix_round"):
                value = data.get(key)
                if value not in (None, ""):
                    ordered[key] = value

            content = json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"
            AtomicWriter.write(cls.STATE_FILE, content)

        return updated_at

    @classmethod
    def check(cls) -> tuple[str, str]:
        if not cls.STATE_FILE.exists():
            return "missing", ""

        try:
            with open(cls.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("checkpoint root must be an object")
        except (json.JSONDecodeError, ValueError):
            backup = cls.STATE_FILE.with_suffix(cls.STATE_FILE.suffix + ".corrupted")
            shutil.copy2(cls.STATE_FILE, backup)
            return "corrupted", backup.name

        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        return "found", content


def _task_lock_path(task_file: Path) -> Path:
    return task_file.with_name(task_file.name + ".lock")


def _require_explicit_status(task: dict, task_file: str) -> None:
    if task.get("status_explicit"):
        return
    print(
        f"ERROR: 任务 #{task['id']} 缺少 `**状态**` 字段，无法继续处理: {task_file}",
        file=sys.stderr,
    )
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# 区域 2：子命令
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_init():
    """初始化工作环境。"""
    for d in (
        "planning/specs",
        "planning/audit-reports",
        "planning/progress-reports",
        ".dual-ai-collab/logs",
        ".dual-ai-collab/checkpoints",
        ".dual-ai-collab/designs",
    ):
        Path(d).mkdir(parents=True, exist_ok=True)
    print("ENV_READY")


def cmd_update(task_num: str, new_status: str, task_file: str):
    """更新任务板中指定任务的状态。"""
    tf = Path(task_file)
    if not tf.exists():
        print(f"ERROR: 任务板不存在: {task_file}")
        sys.exit(1)

    with FileLock(_task_lock_path(tf)):
        text = tf.read_text(encoding="utf-8")
        tasks = MarkdownParser.parse(text)

        # 查找目标任务
        target = None
        for t in tasks:
            if t["id"].lstrip("0") == task_num.lstrip("0"):
                target = t
                break

        if target is None:
            print(f"ERROR: 未找到任务 #{task_num}")
            sys.exit(1)

        _require_explicit_status(target, task_file)

        old_status = target["status"]
        if old_status == new_status:
            print(f"SKIP: 任务 #{task_num} 已经是 {new_status}")
            return

        # 用 sed 风格的精确替换保持原始格式
        # 匹配任务区块内的状态行
        pattern = re.compile(
            r"(## 任务 #0*" + re.escape(task_num.lstrip("0")) + r":.*?\n)"
            r"(.*?)"
            r"(\*\*状态\*\*: )" + re.escape(old_status),
            re.DOTALL,
        )

        new_text, count = pattern.subn(r"\g<1>\g<2>\g<3>" + new_status, text, count=1)
        if count == 0:
            # fallback: 直接行替换
            lines = text.splitlines(True)
            in_task = False
            replaced = False
            for i, line in enumerate(lines):
                if re.match(r"## 任务 #0*" + re.escape(task_num.lstrip("0")) + r":", line):
                    in_task = True
                elif in_task and line.strip() == "---":
                    in_task = False
                elif in_task and f"**状态**: {old_status}" in line:
                    lines[i] = line.replace(f"**状态**: {old_status}", f"**状态**: {new_status}")
                    replaced = True
                    break
            if not replaced:
                print(
                    f"ERROR: 任务 #{task_num} 缺少可替换的状态行，任务板格式可能已损坏: {task_file}",
                    file=sys.stderr,
                )
                sys.exit(1)
            new_text = "".join(lines)

        AtomicWriter.write(tf, new_text)
    print(f"OK: 任务 #{task_num} {old_status} -> {new_status}")

def _check_dep_satisfied(tasks: list[dict], dep_num: str) -> bool:
    """检查单个依赖任务是否已完成（DONE 或 VERIFIED）。"""
    for t in tasks:
        if t["id"].lstrip("0") == dep_num.lstrip("0"):
            return t["status"] in ("DONE", "VERIFIED")
    return False


def _all_deps_satisfied(tasks: list[dict], deps: str) -> bool:
    """检查一个任务的所有依赖是否满足。"""
    if not deps or deps in ("无", "-"):
        return True
    for m in re.finditer(r"#(\d+)", deps):
        if not _check_dep_satisfied(tasks, m.group(1)):
            return False
    return True


def _has_deps(deps: str) -> bool:
    """判断是否有依赖。"""
    return bool(deps) and deps not in ("无", "-", "")


def cmd_select(parallel: bool, task_file: str):
    """选择下一个可执行任务。"""
    tf = Path(task_file)
    if not tf.exists():
        print(f"ERROR: 任务板不存在: {task_file}")
        sys.exit(1)

    text = tf.read_text(encoding="utf-8")
    tasks = MarkdownParser.parse(text)

    for task in tasks:
        _require_explicit_status(task, task_file)

    # 提取所有 OPEN 任务，按优先级排序
    open_tasks = [t for t in tasks if t["status"] == "OPEN"]
    if not open_tasks:
        print("NO_OPEN_TASKS")
        return

    # 按优先级数字排序（P1=1, P2=2, P3=3, P9=9）
    def priority_key(t):
        m = re.match(r"P(\d)", t.get("priority", "P9"))
        return int(m.group(1)) if m else 9
    open_tasks.sort(key=priority_key)

    if parallel:
        # --parallel 模式：只返回无依赖的任务
        result_lines = []
        for t in open_tasks:
            if not _has_deps(t["dependencies"]):
                p = priority_key(t)
                result_lines.append(f"{p}|{t['id']}|{t['dependencies']}")
        if result_lines:
            print("\n".join(result_lines))
        else:
            print("NO_PARALLEL_TASKS")
    else:
        # 默认模式：返回第一个依赖已满足的任务
        for t in open_tasks:
            if _all_deps_satisfied(tasks, t["dependencies"]):
                p = priority_key(t)
                print(f"{p}|{t['id']}|{t['dependencies']}")
                return
        print("NO_EXECUTABLE_TASKS")


def cmd_checkpoint_write(phase: str, extra_args: list[str]):
    """写入 checkpoint。"""
    updated_at = CheckpointStore.write(phase, extra_args)
    print(f"CHECKPOINT: phase={phase} updated_at={updated_at}")


def cmd_checkpoint_check():
    """检查 checkpoint 状态。"""
    status, content = CheckpointStore.check()
    if status == "found":
        print("CHECKPOINT_FOUND")
        print(content, end="")
    elif status == "corrupted":
        print("CHECKPOINT_CORRUPTED")
        print(content)
    else:
        print("NO_CHECKPOINT")


def _read_task_pid(task_num: str) -> int | None:
    pid_file = Path(f".dual-ai-collab/logs/task-{task_num}.pid")
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _task_exit_status(task_num: str) -> str | None:
    exit_file = Path(f".dual-ai-collab/logs/task-{task_num}.exit")
    if not exit_file.exists():
        return None
    try:
        exit_code = int(exit_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "failed"
    return "success" if exit_code == 0 else "failed"


def cmd_run_status(task_num: str):
    """查询任务运行状态。"""
    pid = _read_task_pid(task_num)
    if pid is not None:
        try:
            os.kill(pid, 0)
            print("running")
            return
        except (OSError, ProcessLookupError):
            pass

    exit_status = _task_exit_status(task_num)
    if exit_status is not None:
        print(exit_status)
        return

    pid_file = Path(f".dual-ai-collab/logs/task-{task_num}.pid")
    if pid_file.exists():
        print("stopped")
    else:
        print("not_found")


def cmd_run_stop(task_num: str):
    """终止任务运行。"""
    pid_file = Path(f".dual-ai-collab/logs/task-{task_num}.pid")
    pid = _read_task_pid(task_num)
    if pid is None:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
            print("stopped")
        else:
            print("not_found")
        return

    try:
        os.kill(pid, 15)
    except (OSError, ProcessLookupError):
        pid_file.unlink(missing_ok=True)
        print("stopped")
        return

    deadline = datetime.now(timezone.utc).timestamp() + 5
    while datetime.now(timezone.utc).timestamp() < deadline:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            pid_file.unlink(missing_ok=True)
            print("stopped")
            return
        time.sleep(0.1)

    try:
        os.kill(pid, 9)
    except (OSError, ProcessLookupError):
        pass

    pid_file.unlink(missing_ok=True)
    print("stopped")

def _resolve_stall_minutes(task_num: str, task_file: str) -> int:
    """解析任务级卡死阈值。"""
    tf = Path(task_file)
    if not tf.exists():
        return 3

    text = tf.read_text(encoding="utf-8")
    tasks = MarkdownParser.parse(text)

    target = None
    for t in tasks:
        if t["id"].lstrip("0") == task_num.lstrip("0"):
            target = t
            break

    if target is None:
        return 3

    # 优先级 1：自定义卡死阈值
    if target.get("stall_threshold_minutes"):
        try:
            return int(target["stall_threshold_minutes"])
        except ValueError:
            pass

    # 优先级 2：执行级别
    level = target.get("execution_level", "")
    level_map = {"heavy": 10, "normal": 5, "quick": 3}
    return level_map.get(level, 3)


def cmd_detect(task_num: str, codex_pid: str, task_file: str):
    """检测 Codex 进程是否卡死。"""
    try:
        pid = int(codex_pid)
    except ValueError:
        print(f"ERROR: 非法 PID: {codex_pid}", file=sys.stderr)
        sys.exit(1)

    log_file = Path(f".dual-ai-collab/logs/task-{task_num}.log")
    state_file = Path(f".dual-ai-collab/logs/task-{task_num}.stall-state")
    pid_file = Path(f".dual-ai-collab/logs/task-{task_num}.pid")

    stall_minutes = _resolve_stall_minutes(task_num, task_file)

    # 检查进程是否存活
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        # 进程已退出
        exit_file = Path(f".dual-ai-collab/logs/task-{task_num}.exit")
        exit_code = 1
        trust_exit_file = False
        if pid_file.exists():
            try:
                trust_exit_file = pid_file.read_text().strip() == str(pid)
            except OSError:
                trust_exit_file = False
        if exit_file.exists() and trust_exit_file:
            try:
                exit_code = int(exit_file.read_text().strip())
            except ValueError:
                exit_code = 1
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass
        if exit_code == 0:
            print("SUCCESS")
        else:
            print(f"FAILED (exit code: {exit_code})")
        return

    # 进程存活 — 检查文件变动
    code_exts = (
        "*.py", "*.js", "*.ts", "*.jsx", "*.tsx", "*.go", "*.rs",
        "*.java", "*.c", "*.cpp", "*.vue", "*.svelte", "*.html", "*.css",
    )
    name_args = []
    for i, ext in enumerate(code_exts):
        if i > 0:
            name_args.append("-o")
        name_args.extend(["-name", ext])

    try:
        result = subprocess.run(
            ["find", ".", "("] + name_args + [")",
             "-not", "-path", "./node_modules/*",
             "-not", "-path", "./.git/*",
             "-mmin", f"-{stall_minutes}"],
            capture_output=True, text=True, timeout=10,
        )
        recent_changes = result.stdout.strip().splitlines()[:5]
    except Exception:
        recent_changes = []

    log_size = 0
    try:
        log_size = log_file.stat().st_size
    except FileNotFoundError:
        pass

    if recent_changes:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(f"{log_size}\n")
        print("ACTIVE")
        return

    last_log_size = 0
    if state_file.exists():
        try:
            last_log_size = int(state_file.read_text().strip())
        except (ValueError, FileNotFoundError):
            last_log_size = 0

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{log_size}\n")

    if log_size > last_log_size:
        print("ACTIVE")
    else:
        print("STALLED")

def cmd_summary(task_file: str, report: bool = False):
    """统计任务板进度。"""
    tf = Path(task_file)
    if not tf.exists():
        print(f"ERROR: 任务板不存在: {task_file}")
        sys.exit(1)

    text = tf.read_text(encoding="utf-8")
    tasks = MarkdownParser.parse(text)

    # Finding 4: 与 select/update 对齐——缺少状态字段的任务发出警告
    bad_tasks = [t for t in tasks if not t.get("status_explicit")]
    for t in bad_tasks:
        print(
            f"WARNING: 任务 #{t['id']} 缺少 `**状态**` 字段，已从统计中排除",
            file=sys.stderr,
        )
    valid_tasks = [t for t in tasks if t.get("status_explicit")]

    total = len(valid_tasks)
    counts = {"OPEN": 0, "IN_PROGRESS": 0, "DONE": 0, "VERIFIED": 0,
              "REJECTED": 0, "FAILED": 0}
    for t in valid_tasks:
        s = t["status"]
        if s in counts:
            counts[s] += 1

    completed = counts["DONE"] + counts["VERIFIED"]
    completion_rate = (completed / total * 100) if total > 0 else 0
    audited = counts["VERIFIED"] + counts["REJECTED"]
    audit_rate = (counts["VERIFIED"] / audited * 100) if audited > 0 else 0

    lines = [
        f"总任务: {total}",
        f"OPEN: {counts['OPEN']}",
        f"IN_PROGRESS: {counts['IN_PROGRESS']}",
        f"DONE: {counts['DONE']}",
        f"VERIFIED: {counts['VERIFIED']}",
        f"REJECTED: {counts['REJECTED']}",
        f"FAILED: {counts['FAILED']}",
        f"完成率: {completion_rate:.1f}%",
        f"审计通过率: {audit_rate:.1f}%",
    ]

    for line in lines:
        print(line)

    if report:
        report_dir = Path("planning/progress-reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        report_path = report_dir / f"{ts}-progress.md"
        report_content = f"# 进度报告\n\n生成时间: {ts}\n任务板: {task_file}\n\n"
        report_content += "\n".join(f"- {line}" for line in lines) + "\n"
        AtomicWriter.write(report_path, report_content)
        print(f"报告已写入: {report_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# 区域 3：入口
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="任务管理核心")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="初始化工作环境")

    # update
    p_update = sub.add_parser("update", help="更新任务状态")
    p_update.add_argument("task_num", help="任务编号")
    p_update.add_argument("new_status", help="新状态")
    p_update.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")

    # select
    p_select = sub.add_parser("select", help="选择下一个可执行任务")
    p_select.add_argument("--parallel", action="store_true")
    p_select.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")

    # checkpoint-write
    p_cpw = sub.add_parser("checkpoint-write", help="写入 checkpoint")
    p_cpw.add_argument("phase", help="阶段")
    p_cpw.add_argument("extra", nargs="*", default=[], help="key=value 参数")

    # checkpoint-check
    sub.add_parser("checkpoint-check", help="检查 checkpoint")

    # detect
    p_detect = sub.add_parser("detect", help="检测进程卡死")
    p_detect.add_argument("task_num", help="任务编号")
    p_detect.add_argument("pid", help="进程 PID")
    p_detect.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")

    # run-status
    p_run_status = sub.add_parser("run-status", help="查询任务运行状态")
    p_run_status.add_argument("task_num", help="任务编号")

    # run-stop
    p_run_stop = sub.add_parser("run-stop", help="终止任务运行")
    p_run_stop.add_argument("task_num", help="任务编号")

    # summary
    p_summary = sub.add_parser("summary", help="统计进度")
    p_summary.add_argument("--report", action="store_true",
                           help="生成报告文件到 planning/progress-reports/")
    p_summary.add_argument("task_file", nargs="?", default="planning/codex-tasks.md")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init()
    elif args.command == "update":
        cmd_update(args.task_num, args.new_status, args.task_file)
    elif args.command == "select":
        cmd_select(args.parallel, args.task_file)
    elif args.command == "checkpoint-write":
        cmd_checkpoint_write(args.phase, args.extra)
    elif args.command == "checkpoint-check":
        cmd_checkpoint_check()
    elif args.command == "detect":
        cmd_detect(args.task_num, args.pid, args.task_file)
    elif args.command == "run-status":
        cmd_run_status(args.task_num)
    elif args.command == "run-stop":
        cmd_run_stop(args.task_num)
    elif args.command == "summary":
        cmd_summary(args.task_file, report=args.report)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
