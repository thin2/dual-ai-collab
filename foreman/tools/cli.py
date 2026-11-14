#!/usr/bin/env python3
"""CLI 工具 - 用于命令行和脚本集成。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# lib 用 fcntl 文件锁和 POSIX 进程组，在 Windows 上一导入就失败；先用一句话说清楚
if sys.platform == "win32":
    sys.exit("foreman 只支持 macOS 和 Linux；Windows 上请在 WSL 里安装和使用。\n"
             "foreman runs on macOS and Linux only. On Windows, install and use it inside WSL.")

# 技能根目录加入路径，才能以 lib 包的形式导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import (  # noqa: E402
    CheckpointManager,
    ExecutionConfig,
    ExecutionHistory,
    TaskBoard,
    TaskExecutor,
    TaskStoreError,
    TeamError,
    audit_runs,
    check_team,
    configure_role,
    read_tasks_document,
    remove_role,
    write_tasks_document,
)
from lib.doctor import diagnose, skill_version  # noqa: E402
from lib.plan import KNOWN_STATUSES, check_plan  # noqa: E402
from lib.store import (  # noqa: E402
    DEFAULT_TASKS_MD,
    READY_STATUSES,
    dependency_ids,
    dependency_satisfied,
    describe_error,
)
from lib.team import model_catalog  # noqa: E402
from lib.web import board_status, start_board, stop_board  # noqa: E402
from lib.workflow import (  # noqa: E402
    Workflow,
    delivery_check,
    evidence_template,
    is_direct,
    resolve_commit,
    under_git,
)


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


# 输出里要接着运行的命令都以它开头；它是技能目录下的 bin/foreman
CLI = "foreman"

# init、add、team set 或 config set 之后至少有其中一个
PROJECT_MARKERS = ("planning/tasks.json", "planning/codex-tasks.json", ".task-management/config.json")


def find_project_root(start: Path) -> Path | None:
    """从 start 向上找有任务板或配置的目录；找不到返回 None"""
    for folder in [start, *start.parents]:
        if any((folder / marker).is_file() for marker in PROJECT_MARKERS):
            return folder
        # 不越过 git 仓库的边界：上级目录里其他项目的任务板不属于这个仓库
        if (folder / ".git").exists():
            break
    return None


def resolve_root(command: str) -> Path:
    """命令使用的项目根目录：init 固定用当前目录，其余命令向上查找，找不到时退回当前目录"""
    cwd = Path.cwd()
    if command == "init":
        return cwd
    found = find_project_root(cwd)
    if found is None:
        # models 不需要项目；doctor 自己会报告没有找到项目
        if command not in ("models", "doctor"):
            print(f"提示: {cwd} 及其上级目录没有任务板或配置，按当前目录处理；新项目先运行 {CLI} init", file=sys.stderr)
        return cwd
    if found != cwd:
        print(f"项目根目录: {found}", file=sys.stderr)
    return found


def _input_file(root: Path, value: str) -> Path:
    """命令行给出的输入文件：相对路径先按当前目录找，找不到再按项目根目录找"""
    path = Path(value)
    if not path.is_absolute() and not path.exists() and (root / path).exists():
        return root / path
    return path


def _read_input(root: Path, value: str, what: str) -> str:
    """读取命令行给出的输入文件；读不了时说明是哪个文件、为什么"""
    path = _input_file(root, value)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        searched = "" if path.is_absolute() else f"：当前目录和项目根目录 {root} 下都没有"
        raise ValueError(f"找不到{what} {value}{searched}") from None
    except (OSError, ValueError) as error:
        raise ValueError(f"读不了{what} {path}（{describe_error(error)}）") from error


def _read_json(root: Path, value: str, what: str):
    """读取命令行给出的 JSON 文件；- 表示标准输入"""
    raw = sys.stdin.read() if value == "-" else _read_input(root, value, what)
    try:
        return json.loads(raw)
    except ValueError as error:
        source = "标准输入" if value == "-" else value
        raise ValueError(f"{what} {source} 不是合法的 JSON（{describe_error(error)}）") from error


def cmd_init(args):
    """初始化项目"""
    project_root = args.root
    outer = find_project_root(project_root)
    if outer not in (None, project_root):
        print(f"注意: 上级目录 {outer} 已有任务板；这里将成为独立的项目，本目录内的命令从此使用它", file=sys.stderr)

    (project_root / "planning" / "specs").mkdir(parents=True, exist_ok=True)
    (project_root / ".task-management").mkdir(parents=True, exist_ok=True)

    task_file = project_root / DEFAULT_TASKS_MD
    if not task_file.with_suffix(".json").exists():
        # 有旧的 codex-tasks.json 时读出来写到新文件，不能用空任务板盖住它
        write_tasks_document(read_tasks_document(task_file), task_file)

    config = ExecutionConfig(project_root)
    config.save()

    print("项目初始化完成")
    print(f"任务板: {task_file}")
    print(f"配置: {config.config_file}")


def cmd_select(args):
    """下一个可以开始的任务：batch 的第一项"""
    board = TaskBoard.load(args.root)
    config = ExecutionConfig(args.root)
    selection = board.select_batch(config.get_roles(), config.get_max_parallel())

    if selection["batch"]:
        task = selection["batch"][0]
        print(f"下一个任务: {task['id']} - {task.get('title', '未命名')}")
        print(f"类型: {task.get('type', 'feature')}")
        print(f"预估: {task.get('estimated_hours', 0)}小时")
        print(f"依赖: {task.get('dependencies', '无')}")
        print(f"执行: {_who(task)}")
        print(f"开始: {_start_command(task)}")
        return

    tasks = board.get_all_tasks()
    if not tasks:
        print("任务板没有任务")
        return
    if all(task.get("status") == "DONE" for task in tasks):
        print("所有任务都已完成")
        return
    print("没有可以开始的任务")
    for task in tasks:
        status = task.get("status", "PENDING")
        if status != "DONE" and status not in READY_STATUSES:
            print(f"未完成: {task['id']} {status} - {task.get('title', '未命名')}")
    for item in selection["skipped"]:
        print(f"跳过: {item['id']} - {item['reason']}")


def _who(task: dict) -> str:
    return f"派给角色 {task['role']}" if task.get("role") else "当前会话直接执行"


def cmd_add(args):
    """把 JSON 文件里的任务写入任务板"""
    data = _read_json(args.root, args.file, "任务文件")
    tasks = data["tasks"] if isinstance(data, dict) and "tasks" in data else data
    if isinstance(tasks, dict):
        tasks = [tasks]
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("文件内容应是一个任务对象、任务列表，或 {\"tasks\": [...]}")
    written = TaskBoard.load(args.root).add_tasks(tasks, replace=args.replace)
    print(f"已写入 {len(written)} 个任务: {'、'.join(written)}")
    # 任务已经写入；这里只是把 validate 会对它们报的问题提前说出来
    try:
        report = check_plan(args.root)
    except ValueError as error:
        report = {"board": [], "warnings": []}
        print(f"注意: 没能运行规划检查（{error}）", file=sys.stderr)
    problems = [item for item in report["board"] if item["task"] in written]
    warnings = [item for item in report["warnings"] if item["task"] in written]
    if problems:
        print(f"其中 {len(problems)} 处要在执行前补齐（改好文件后用 add --replace 重新写入）：")
        for item in problems:
            print(f"  {item['task']} {item['field']}: {item['problem']}")
    if warnings:
        print(f"任务粒度提醒 {len(warnings)} 处（不阻止执行；要拆就改好文件后用 add --replace 重新写入）：")
        for item in warnings:
            print(f"  {item['task']} {item['field']}: {item['problem']}")
    print(f"接着运行 {CLI} validate 检查字段、依赖和角色")


def cmd_show(args):
    """查看任务板，或某个任务的完整执行上下文"""
    board = TaskBoard.load(args.root)
    tasks = board.get_all_tasks()
    if args.mermaid:
        lines = ["graph TD"]
        for task in tasks:
            title = str(task.get("title", "")).replace('"', "'")
            lines.append(f'  {task["id"]}["{task["id"]}: {title}"]')
            lines.extend(f"  {dep} --> {task['id']}" for dep in dependency_ids(task.get("dependencies")))
        print("\n".join(lines))
        return
    if not args.task_id:
        if args.json:
            _print_json(tasks)
            return
        if not tasks:
            print("任务板没有任务")
        for task in tasks:
            status = task.get("status", "PENDING")
            line = f"{task['id']}\t{status}\t{_who(task)}\t{task.get('title', '')}"
            waiting = [dep for dep in dependency_ids(task.get("dependencies"))
                       if not dependency_satisfied(tasks, dep)]
            if waiting and status != "DONE":
                line += "\t等待 " + "、".join(f"#{dep}" for dep in waiting)
            print(line)
        return
    task = board.get_task(args.task_id)
    if not task:
        raise ValueError(f"任务 {args.task_id} 不存在")
    if args.json:
        _print_json(task)
        return
    print(board.build_context(task))
    print("## 当前状态")
    print(f"状态: {task.get('status', 'PENDING')}")
    print(f"执行: {_who(task)}")
    if task.get("runtime_dependencies"):
        print("运行依赖: " + "、".join(task["runtime_dependencies"]))
    if task.get("execution_id"):
        print(f"执行编号: {task['execution_id']}")
    steps = _next_steps(Workflow(args.root), task)
    if steps:
        print("\n## 下一步")
        print("\n".join(steps))


def _start_command(task: dict) -> str:
    if task.get("role"):
        return f"{CLI} run {task['id']} --dispatcher <调度模型ID>   # 派给角色 {task['role']}；先 team check 和 preflight"
    return f"{CLI} execution begin {task['id']}   # 登记开始，然后由当前会话实现"


def _next_steps(workflow: Workflow, task: dict) -> list[str]:
    """按任务当前状态给出接下来要运行的命令；命令里的任务 ID 会换成它当前的执行记录"""
    tid, status = task["id"], task.get("status", "PENDING")
    board, record = workflow.board, workflow.current_record(task)
    if status == "DONE":
        return ["已集成，不需要操作"]
    if status in READY_STATUSES:
        missing = [field for field in ("files", "runtime_dependencies", "acceptance") if not task.get(field)]
        if missing:
            return [f"缺 {'、'.join(missing)}，不能登记开始：用 add --replace 补齐"
                    "（不补也可以继续用 update 和 integrate，但没有文件基线和验收记录）"]
        config = ExecutionConfig(workflow.root)
        selection = board.select_batch(config.get_roles(), config.get_max_parallel())
        if tid in {item["id"] for item in selection["batch"]}:
            return [_start_command(task)]
        reason = next((item["reason"] for item in selection["skipped"] if item["id"] == tid), None)
        return [f"暂时不能开始：{reason}" if reason else f"暂时不能开始；运行 {CLI} batch 查看原因"]
    if not record:
        if task.get("execution_id"):
            return [f"任务板登记的执行记录 {task['execution_id']} 不存在："
                    f"恢复 {workflow.history.history_dir.relative_to(workflow.root)}/{task['execution_id']}.json 后再继续"]
        if status == "BLOCKED":
            return ["等用户处理阻塞原因", f"{CLI} update {tid} PENDING --reset-retries   # 没有执行记录的旧任务"]
        return ["没有执行记录的旧任务：用 update 改状态，用 integrate 确认集成"]
    if status == "IN_PROGRESS":
        if is_direct(record):
            return ["由当前会话实现，只改 files 列出的路径",
                    f"{CLI} execution finish {tid} --outcome completed   # 没做完用 failed，被打断用 interrupted"]
        return ["派发进行中。run 结束时会自动登记；手工用 Task 派发的，返回后运行：",
                f"{CLI} execution finish {tid} --outcome returned   # 或 permission_rejected、failed、interrupted"]
    if status == "AWAITING_REVIEW":
        steps = [f"{CLI} execution inspect {tid}   # 文件变化和 notices"]
        if record.details.get("audit", {}).get("status") not in {"passed", "not_applicable"}:
            steps.append(f"{CLI} execution audit {tid}   # 核对实际模型，通过后才能验收")
        evidence = _evidence_path(board, task)
        relative = evidence.relative_to(board.project_root)
        steps.append(f"编辑 {relative}，逐项填写证据" if evidence.exists() else
                     f"{CLI} acceptance {tid} --template   # 生成 {relative}，逐项填写证据")
        steps.append(f"{CLI} execution accept {tid} --evidence-file {relative}")
        steps.append(f"不完整时: {CLI} execution retry {tid} --reason \"已完成的部分和还要做的事\"")
        if (record.details.get("dispatch_outcome") == "interrupted"
                and not (record.details.get("transport") or {}).get("timed_out")):
            steps.append(f"是用户叫停的: {CLI} execution pause {tid} --reason \"用户为什么叫停、已完成的部分\"   # 不计失败次数")
        return steps
    if status == "AWAITING_INTEGRATION":
        if not under_git(workflow.root):
            return ["项目不在 git 仓库里，没有提交可以核对：确认成果已经保存好（例如做了备份）",
                    f"{CLI} integrate {tid} --no-git --note \"<成果保存在哪里>\""]
        return ["用户授权后提交 files 和 runtime_dependencies 里的改动", f"{CLI} integrate {tid} --commit <提交 SHA>"]
    if status == "BLOCKED":
        return ["等用户处理阻塞原因", f"{CLI} execution unblock {tid} --reason \"<用户的处理结果>\""]
    return []


def cmd_status(args):
    """显示任务状态"""
    board = TaskBoard.load(args.root)
    stats = board.get_statistics()

    print(f"总任务: {stats['total']}")
    print("\n按状态:")
    for status, count in stats['by_status'].items():
        print(f"  {status}: {count}")


def cmd_plan_execution(args):
    """规划任务执行"""
    executor = TaskExecutor(args.root)

    try:
        if args.json:
            _print_json(executor.plan_execution(args.task_id))
        else:
            print(executor.get_execution_info(args.task_id))
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_batch(args):
    """规划下一批可并行执行的任务"""
    plan = TaskExecutor(args.root).plan_batch()
    if args.json:
        _print_json(plan)
        return
    if not plan["batch"]:
        print("没有可以开始的任务")
    for item in plan["batch"]:
        target = f"{item['droid']}（固定模型 {item['model']}）" if item["role"] else "当前会话直接执行"
        print(f"开始: {item['task_id']} {item['task_title']} → {target}")
    for item in plan["skipped"]:
        print(f"跳过: {item['id']} - {item['reason']}")


def cmd_validate(args):
    """规划检查：派发前找出会被拒绝或永远轮不到的任务"""
    report = check_plan(args.root)
    if args.json:
        _print_json(report)
    else:
        if report["board"]:
            print(f"任务板问题 {len(report['board'])} 个：")
            for item in report["board"]:
                print(f"  {item['task'] or '-'} {item['field']}: {item['problem']}")
        if report["team"]:
            print(f"团队未就绪 {len(report['team'])} 个：")
            for item in report["team"]:
                print(f"  {item['role']}（任务 {'、'.join(item['tasks'])}）: {item['problem']}")
        if report["warnings"]:
            print(f"任务粒度提醒 {len(report['warnings'])} 个（不影响退出码；确认是有意这样拆的，否则拆开后用 add --replace 重新写入）：")
            for item in report["warnings"]:
                print(f"  {item['task']} {item['field']}: {item['problem']}")
        if report["ok"]:
            count = len(report["checked"])
            print(f"规划检查通过：{count} 个未完成任务的字段、依赖和角色没有发现问题" if count else "没有未完成的任务需要检查")
        if report["direct"]:
            print(f"其中 {len(report['direct'])} 个没有 role，由当前会话直接执行：{'、'.join(report['direct'])}")
    if not report["ok"]:
        sys.exit(1)


def cmd_update_status(args):
    """更新任务状态"""
    if args.status not in KNOWN_STATUSES:
        upper = args.status.upper()
        hint = f"状态要大写，是不是 {upper}？" if upper in KNOWN_STATUSES else ""
        raise ValueError(f"状态 {args.status} 无效。{hint}可用的状态: {'、'.join(sorted(KNOWN_STATUSES))}")
    board = TaskBoard.load(args.root)

    try:
        board.update_task_status(args.task_id, args.status, reset_retries=args.reset_retries,
                                 require_unmanaged=True)
        print(f"任务 {args.task_id} 状态已更新为 {args.status}")
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_fail(args):
    """记录一次失败，按重试上限决定回到 PENDING 还是 BLOCKED"""
    board = TaskBoard.load(args.root)
    max_retries = ExecutionConfig(args.root).get_max_retries()
    try:
        failures, status = board.record_failure(args.task_id, max_retries, block=args.block,
                                                reason=args.reason or "", require_unmanaged=True)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"任务 {args.task_id} 第 {failures} 次失败（上限 {max_retries} 次重试）→ {status}")
    if args.reason:
        print(f"原因: {args.reason}")


def cmd_integrate(args):
    """确认任务的提交已在目标仓库中，记录集成并标记 DONE"""
    workflow = Workflow(args.root)
    if args.no_git:
        if args.target:
            raise ValueError("--no-git 记录的是本项目里已验收的内容，不能和 --target 一起用")
        task = workflow.integrate(args.task_id, None, args.root.resolve(), args.note or "")
        digest = (task.get("integration") or {}).get("digest")
        print(f"任务 {args.task_id} 已集成（没有提交" + (f"，已验收内容的摘要 {digest[:12]}" if digest else "") + "）→ DONE")
    else:
        repo = Path(args.target or args.root).resolve()
        commit = resolve_commit(repo, args.commit)
        task = workflow.integrate(args.task_id, commit, repo, args.note or "")
        print(f"任务 {args.task_id} 已集成（{commit[:12]}）→ DONE")
    if task.get("execution_id"):
        _warn_processes(workflow, task["execution_id"])
    _warn_set_aside(workflow)


def cmd_checkpoint(args):
    """Checkpoint 管理"""
    checkpoint = CheckpointManager(args.root)

    if args.action == "check":
        print(checkpoint.check())
    elif args.action == "save":
        if not args.phase:
            raise ValueError(f"save 需要 --phase，例如 {CLI} checkpoint save --phase developing")
        data = {}
        for item in args.data or []:
            key, separator, value = item.partition("=")
            if not separator or not key:
                raise ValueError(f"--data 的每一项要写成 key=value，收到的是 {item!r}")
            data[key] = value
        try:
            entering = args.phase == "developing" and (checkpoint.load() or {}).get("phase") != "developing"
        except ValueError:
            entering = False
        checkpoint.save(args.phase, **data)
        print(f"Checkpoint 已保存: phase={args.phase}")
        if entering:
            # 只在进入开发阶段时说一次：之后每次保存都重复就成了噪音
            board = board_status(args.root)
            print(f"看板: {board['url']}" if board["listed"] else
                  f"提示: 想在浏览器里看任务板和进度，运行 {CLI} web start（需要 Flask；不用可以忽略）")
    elif args.action == "clear":
        checkpoint.clear()
        print("Checkpoint 已清除")


def cmd_config(args):
    """配置管理"""
    config = ExecutionConfig(args.root)

    if args.action == "show":
        _print_json(config.get_all_settings())
    elif args.action == "set":
        if not args.key_value or "=" not in args.key_value:
            raise ValueError(f"set 需要 key=value，例如 {CLI} config set parallel.max_parallel=3")
        key, value = (part.strip() for part in args.key_value.split("=", 1))
        section, _, name = key.partition(".")
        if section == "execution" and name in config.DEFAULT_CONFIG["execution"]:
            if not value:
                raise ValueError(f"{key} 需要一个 droid 名，例如 {CLI} config set {key}=worker")
            config.set_droid_for_complexity(name, value)
            print(f"已设置 {name} → {value}")
        elif section == "parallel" and name in config.MINIMUMS:
            try:
                number = int(value)
            except ValueError:
                raise ValueError(f"{key} 要是整数，收到的是 {value!r}") from None
            if number < config.MINIMUMS[name]:
                raise ValueError(f"{key} 不能小于 {config.MINIMUMS[name]}")
            config.config["parallel"][name] = number
            config.save()
            print(f"已设置 {key} = {number}")
        else:
            settable = [f"execution.{name}" for name in config.DEFAULT_CONFIG["execution"]]
            settable += [f"parallel.{name}" for name in config.MINIMUMS]
            raise ValueError(f"不支持的配置键: {key}。可以设置的有: {'、'.join(settable)}；"
                             f"角色用 {CLI} team set 配置")


def cmd_models(args):
    """列出用户自己配置的模型（不显示密钥）"""
    catalog = model_catalog(Path(args.settings) if args.settings else None, args.search, args.recommend)
    models = catalog["models"]
    if args.json:
        _print_json(catalog if args.catalog else models)
        return
    print(f"共 {catalog['total']} 个模型，当前显示 {catalog['matches']} 个；完整 ID 区分线路。")
    for model in models:
        marker = "推荐" if model["recommended"] else ""
        print(f"{model['id']}\t{model['name']}\t{model['provider']}\t{model['endpoint']}\t{marker}")
    print(catalog["selection"])


def cmd_team(args):
    """固定模型角色管理"""
    root = args.root
    settings = Path(args.settings) if getattr(args, "settings", None) else None

    if args.action == "show":
        roles = ExecutionConfig(root).get_roles()
        if args.json:
            _print_json(roles)
        elif not roles:
            print("还没有配置角色")
        else:
            for role, entry in sorted(roles.items()):
                mode = "只读" if entry.get("read_only") else "可修改"
                print(f"{role}\t{entry['droid']}\t{entry['model']}\t{mode}\t{entry.get('description', '')}")
    elif args.action == "set":
        instructions = None
        if args.instructions_file:
            instructions = _read_input(root, args.instructions_file, "系统提示文件")
        path = configure_role(
            root,
            args.role,
            args.model,
            args.description,
            instructions=instructions,
            read_only=args.read_only,
            force=args.force,
            settings_path=settings,
        )
        print(f"已配置角色 {args.role} → {args.model}")
        print(f"Droid 文件: {path}")
        print("注意：新建或修改的 droid 文件要在新的 droid 会话中才会生效")
    elif args.action == "remove":
        if remove_role(root, args.role):
            print(f"已删除角色 {args.role}")
        else:
            print(f"没有角色 {args.role}")
    elif args.action == "check":
        results = check_team(root, settings_path=settings)
        if args.json:
            _print_json(results)
        elif not results:
            print("还没有配置角色，没有需要检查的；没有 role 的任务由当前会话直接执行")
        for item in results:
            if not args.json:
                state = "正常" if item["ok"] else "不可用"
                print(f"{item['role']}\t{item['model']}\t{state}")
                for problem in item["problems"]:
                    print(f"  - {problem}")
        if any(not item["ok"] for item in results):
            sys.exit(2)
    elif args.action == "audit":
        records = audit_runs(root, limit=args.limit)
        if args.json:
            _print_json(records)
        elif not records:
            print("没有找到本项目子 Agent 的运行记录")
        for record in records if not args.json else []:
            state = "一致" if record["ok"] else "不一致"
            print(f"{state}\t{record['role']}\t预期 {record['expected']}\t实际 {record['actual']}\t{record['title']}")
        if any(not record["ok"] for record in records):
            sys.exit(2)


def cmd_history(args):
    """查看执行历史"""
    history = ExecutionHistory(args.root)

    if args.task_id:
        records = history.get_task_history(args.task_id)
    else:
        records = history.get_all_history()

    _warn_unreadable(history)
    if not records:
        print("没有执行记录")
        return

    for record in records[:args.limit]:
        status_symbol = "✓" if record.status == "success" else "✗"
        duration = f"{record.duration_seconds:.1f}s" if record.duration_seconds is not None else (
            "运行中" if record.status == "running" else "结束时间未知"
        )
        model = f" ({record.model})" if getattr(record, "model", None) else ""
        print(f"{status_symbol} {record.task_id} - {record.start_time} - {duration} - {record.droid}{model}")


def _warn_unreadable(history: ExecutionHistory) -> None:
    if history.unreadable:
        print(f"注意: {len(history.unreadable)} 个执行记录读不出来，已跳过（在 {history.history_dir} 下）: "
              + "、".join(history.unreadable), file=sys.stderr)


def _evidence_path(board: TaskBoard, task: dict) -> Path:
    # 任务板所在目录的改动不算范围外改动，证据放这里不会被 accept 拒绝
    return board.task_file.parent / f"acceptance-{task['id']}.json"


def cmd_acceptance(args):
    """提取验收命令，或生成验收证据框架"""
    board = TaskBoard.load(args.root)
    task = board.get_task(args.task_id)
    if not task:
        raise ValueError(f"任务 {args.task_id} 不存在")
    if args.template:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(task["id"])):
            raise ValueError(f"任务编号 {task['id']!r} 不能用作文件名：只能含字母、数字、下划线和连字符")
        record = Workflow(args.root).current_record(task)
        undeclared = ((record.details.get("undeclared") or {}).get("paths") or []) if record else []
        template = evidence_template(task, undeclared, record.execution_id if record else None)
        path = _evidence_path(board, task)
        if path.exists() and not args.force:
            raise ValueError(f"{path} 已存在，直接编辑它；要重新生成用 --force（会覆盖已填写的内容）")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"验收证据框架: {path}")
        print("逐项运行或观察后填写：每项 status 改为 passed 并写明 evidence，inspection 写实际文件审查结论。"
              "没通过的条件不要写 passed，修复后重验。")
        if not record or record.status == "running" or record.details.get("recovery"):
            print("注意: 这个任务当前没有已登记结束、等待验收的执行。证据要在 execution finish 之后取得："
                  "之前填好的文件，或为另一次执行生成的框架，execution accept 都会拒绝。", file=sys.stderr)
        else:
            print(f"框架里的 execution_id 是这次执行（{record.execution_id}），不要改：证据只对这次执行有效。")
        if undeclared:
            print(f"执行期间声明范围外有改动：{'、'.join(undeclared)}；在 undeclared 字段写明来源和处理结论")
        print(f"填好后运行: {CLI} execution accept {task['id']} --evidence-file {path.relative_to(board.project_root)}")
        return
    if task.get("acceptance"):
        from lib.workflow import requirements
        _print_json(requirements(task))
        return
    commands = board.get_acceptance_commands(args.task_id)

    if not commands:
        print(f"任务 {task['id']} 没有验收条件：没有 acceptance 字段，“验收”章节里也没有反引号包住的命令")
        return

    for i, cmd in enumerate(commands, 1):
        print(f"{i}. {cmd}")


def cmd_preflight(args):
    from lib.probe import run_probe
    result = run_probe(args.root, args.dispatcher)
    _print_json(result)
    if not result["ok"]:
        sys.exit(2)


def cmd_run(args):
    from lib.runner import run_task
    result = run_task(args.root, args.task_id, args.dispatcher, timeout=args.timeout)
    _print_json(result)
    if result["dispatch_outcome"] != "returned" or result["audit"]["status"] != "passed":
        sys.exit(2)


def cmd_execution(args):
    workflow = Workflow(args.root)
    if args.action not in {"begin", "recover", "sync"}:
        args.id = workflow.resolve_execution_id(args.id)
    if args.action == "begin":
        _print_json(workflow.begin(args.id))
    elif args.action == "finish":
        _print_json(workflow.finish(args.id, args.outcome, args.ended_at))
        _warn_processes(workflow, args.id)
    elif args.action == "inspect":
        _print_json(workflow.inspect(args.id))
    elif args.action == "audit":
        result = workflow.audit(args.id)
        _print_json(result)
        if result["status"] not in {"passed", "not_applicable"}:
            sys.exit(2)
    elif args.action == "accept":
        evidence = _read_json(args.root, args.evidence_file, "验收证据文件")
        written_at = None if args.evidence_file == "-" else _input_file(args.root, args.evidence_file).stat().st_mtime
        task = workflow.accept(args.id, evidence, written_at)
        record = workflow.current_record(task)
        print(f"验收已记录：任务 {task['id']} → {task['status']}")
        outcome = record.details["dispatch_outcome"]
        if outcome not in {"returned", "completed"}:
            # 验收看的是现有文件；这次执行是怎么结束的，仍按原样留在记录里
            print(f"{'执行' if is_direct(record) else '派发'}结果仍记为 {outcome}，不因验收通过而改写")
        print("下一步:")
        for step in _next_steps(workflow, task):
            print(f"  {step}")
    elif args.action in {"retry", "block"}:
        workflow.retry(args.id, args.reason, args.action == "block")
        print("检查结论和续做原因已保存，原有文件保留")
        _warn_processes(workflow, args.id)
    elif args.action == "pause":
        task = workflow.pause(args.id, args.reason)
        print(f"已记为用户叫停：任务 {task['id']} 回到 PENDING，不计失败次数"
              f"（仍是 {int(task.get('failed_attempts', 0))} 次），原有文件保留")
        print(f"用户同意继续时: {_start_command(task)}")
        print("重新开始时任务上下文会带上这段说明；先看已有改动，在它之上接着做")
        _warn_processes(workflow, args.id)
    elif args.action == "track":
        entry = workflow.track(args.id, args.pid, args.label)
        print(f"已登记进程 {entry['pid']}（{entry['label']}）；finish 和 integrate 时还在运行会提醒关闭")
    elif args.action == "unblock":
        workflow.unblock(args.id, args.reason)
        print("已按用户决定解除阻塞：任务回到 PENDING，失败次数清零")
    elif args.action == "recover":
        from dataclasses import asdict
        current = {task.get("execution_id") for task in workflow.board.get_all_tasks()}
        records = [dict(asdict(record), current=record.execution_id in current)
                   for record in workflow.history.get_all_history()
                   if record.details.get("managed") and not record.details.get("integration")]
        _warn_unreadable(workflow.history)
        if records or workflow.history.unreadable:
            instruction = ("先确认子进程已结束；running 不代表仍存活。未知结束时间用 finish --outcome interrupted。"
                           "再 inspect，审查文件后 accept、retry 或 block；是用户叫停的用 pause，不计失败次数。不要自动重跑。"
                           "details.mode 为 direct 的记录是当前会话直接执行的：仍是 running 时检查已有改动后接着做，"
                           "做完用 finish --outcome completed。"
                           "current 为 false 的记录已被后续派发替代或未登记到任务板，仅供查阅。")
        else:
            instruction = f"没有尚未集成的执行记录，不需要恢复。任务板的状态用 {CLI} show 查看。"
        _print_json({"records": records, "instruction": instruction})
    elif args.action == "sync":
        workflow.sync()
        if not workflow.checkpoint_set_aside:
            print("Checkpoint 已从实际任务板同步，保留其他上下文")
    _warn_set_aside(workflow)


def _warn_processes(workflow: Workflow, execution_id: str) -> None:
    alive = workflow.running_processes(execution_id)
    if alive:
        print("注意: 这次执行登记的进程还在运行：" + "；".join(f"{item['label']}（PID {item['pid']}）" for item in alive)
              + "。不再需要的现在关掉，要留着的告诉用户它还开着", file=sys.stderr)


def cmd_web(args):
    """Web 看板：查看是否在运行，启动或关闭"""
    root = args.root.resolve()
    if args.action == "start":
        if not any((root / marker).is_file() for marker in PROJECT_MARKERS):
            raise ValueError(f"{root} 没有任务板或配置；先 cd 到项目目录，新项目先运行 {CLI} init")
        result = start_board(root, args.port)
        if args.json:
            _print_json(result)
        elif result["action"] == "started":
            print(f"看板已启动: {result['url']}")
            print(f"只监听本机；日志在 {result['log']}。用完后运行 {CLI} web stop 关闭")
        elif result["action"] == "added":
            print(f"端口 {result['port']} 上已有看板在运行，已把这个项目登记进去: {result['url']}")
        else:
            print(f"看板已在运行: {result['url']}")
    elif args.action == "stop":
        result = stop_board(root)
        if args.json:
            _print_json(result)
        elif result["stopped"]:
            print(f"看板已关闭（端口 {result['port']}）")
        elif result["port"]:
            print("看板进程已经不在，启动记录已清除")
        else:
            print(f"这个项目没有由 {CLI} web start 启动的看板")
            board = board_status(root)
            if board["running"]:
                print(f"端口 {board['port']} 上的看板是别处启动的：在启动它的项目里运行 {CLI} web stop，或结束那个进程")
    else:
        result = board_status(root)
        if args.json:
            _print_json(result)
        elif result["listed"]:
            print(f"看板正在运行: {result['url']}")
        elif result["running"]:
            print(f"端口 {result['port']} 上有看板在运行，但没有登记这个项目；运行 {CLI} web start 把它加进去")
        else:
            print(f"看板没有运行；想在浏览器里看任务板和进度，运行 {CLI} web start")


def _warn_set_aside(workflow: Workflow) -> None:
    if workflow.checkpoint_set_aside:
        print(f"注意: 原来的 checkpoint 读不出来，已另存为 {workflow.checkpoint_set_aside}；"
              "任务进度已按任务板重建，规格路径等其他上下文要从那个文件里找回，再用 checkpoint save 补上",
              file=sys.stderr)


def cmd_delivery(args):
    result = delivery_check(args.root, args.commit, args.paths)
    _print_json(result)
    if not result["ok"]:
        sys.exit(2)


LEVEL_LABELS = {"ok": "正常", "note": "注意", "problem": "问题"}


def cmd_doctor(args):
    """只读自检：环境和项目数据里有什么会让命令用不了"""
    cwd = Path.cwd()
    items = diagnose(find_project_root(cwd), cwd)
    problems = sum(item["level"] == "problem" for item in items)
    if args.json:
        _print_json({"ok": not problems, "items": items})
    else:
        for item in items:
            print(f"[{LEVEL_LABELS[item['level']]}] {item['name']}: {item['detail']}")
            if item["fix"]:
                print(f"       处理: {item['fix']}")
        notes = sum(item["level"] == "note" for item in items)
        print(f"\n{problems} 个问题，{notes} 个注意事项。"
              f"规划本身的问题用 {CLI} validate 检查，模型服务能否连通用 {CLI} team check 检查")
    if problems:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=CLI, description="Foreman 任务管理 CLI")
    parser.add_argument("--version", action="version", version=f"{CLI} {skill_version()}")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    subparsers.add_parser("init", help="初始化项目")
    p = subparsers.add_parser("doctor", help="只读自检：环境、任务板、配置、checkpoint 和执行记录；有问题时退出码 1")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    subparsers.add_parser("select", help="下一个可以开始的任务（batch 的第一项）")
    subparsers.add_parser("status", help="显示任务统计")

    p = subparsers.add_parser("add", help="把 JSON 文件里的任务写入任务板")
    p.add_argument("--file", required=True, help="任务对象、任务列表或 {\"tasks\": [...]}；- 表示标准输入")
    p.add_argument("--replace", action="store_true", help="改写编号相同且处于待开始状态的任务（返工记录保留）")

    p = subparsers.add_parser("show", help="查看任务板；带任务 ID 时输出该任务的完整执行上下文")
    p.add_argument("task_id", nargs="?", help="任务 ID（可选）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--mermaid", action="store_true", help="输出整个任务板的 Mermaid 依赖图")

    p = subparsers.add_parser("plan-execution", help="规划单个任务的执行")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--json", action="store_true", help="输出 JSON（含 task_args）")

    p = subparsers.add_parser("batch", help="规划下一批可并行执行的任务")
    p.add_argument("--json", action="store_true", help="输出 JSON（派发的任务含 task_args）")

    p = subparsers.add_parser("validate", help="规划检查：缺字段、依赖不存在或成环、角色未配置，有问题时退出码 1；"
                                               "任务过大只提醒")
    p.add_argument("--json", action="store_true", help="JSON 输出")

    p = subparsers.add_parser("update", help="更新任务状态")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("status", help="新状态")
    p.add_argument("--reset-retries", action="store_true", help="同时把失败次数清零")

    p = subparsers.add_parser("fail", help="记录一次失败（超过重试上限时改为 BLOCKED）")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--reason", help="失败原因")
    p.add_argument("--block", action="store_true", help="直接改为 BLOCKED，不再重试（例如模型不可用）")

    p = subparsers.add_parser("integrate", help="确认集成，标记 DONE 并解锁依赖它的任务；--commit 和 --no-git 二选一")
    p.add_argument("task_id", help="任务 ID")
    how = p.add_mutually_exclusive_group(required=True)
    how.add_argument("--commit", help="包含该任务修改的提交")
    how.add_argument("--no-git", action="store_true",
                     help="项目不在 git 仓库里：不核对提交，记录已验收内容的摘要；必须加 --note")
    p.add_argument("--target", help="目标仓库路径（默认项目根目录）")
    p.add_argument("--note", help="说明；--no-git 时必填，写明成果保存在哪里")

    p = subparsers.add_parser("checkpoint", help="Checkpoint 管理")
    p.add_argument("action", choices=["check", "save", "clear"], help="操作")
    p.add_argument("--phase", help="阶段名称（save 时必需）")
    p.add_argument("--data", nargs="+", help="数据 key=value（save 时可选）")

    p = subparsers.add_parser("config", help="配置管理")
    p.add_argument("action", choices=["show", "set"], help="操作")
    p.add_argument("key_value", nargs="?", help="配置项 key=value（set 时必需）")

    p = subparsers.add_parser("models", help="列出自己配置的模型（BYOK）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--settings", help="settings.json 路径（默认 ~/.factory/settings.json）")
    p.add_argument("--search", default="", help="按 ID、名称、provider 或端点搜索，不改变全量目录")
    p.add_argument("--recommend", action="append", default=[], help="推荐 ID，只调整排序，不隐藏其他模型")
    p.add_argument("--catalog", action="store_true", help="JSON 包含总数与选择说明")

    p = subparsers.add_parser("team", help="固定模型角色管理")
    team = p.add_subparsers(dest="action", required=True)
    t = team.add_parser("show", help="查看角色")
    t.add_argument("--json", action="store_true")
    t = team.add_parser("set", help="新增或修改角色，并生成对应的项目级 droid")
    t.add_argument("role", help="角色名，例如 frontend")
    t.add_argument("--model", required=True, help="模型 ID，来自 models 命令的第一列")
    t.add_argument("--description", required=True, help="角色职责")
    t.add_argument("--instructions-file", help="自定义系统提示文件（可选）")
    t.add_argument("--read-only", action="store_true", help="只读角色，例如审查")
    t.add_argument("--force", action="store_true", help="覆盖非本技能生成的同名 droid 文件")
    t.add_argument("--settings", help="settings.json 路径（默认 ~/.factory/settings.json）")
    t = team.add_parser("remove", help="删除角色及其 droid 文件")
    t.add_argument("role")
    t = team.add_parser("check", help="派发前检查角色的模型是否可用")
    t.add_argument("--json", action="store_true")
    t.add_argument("--settings", help="settings.json 路径（默认 ~/.factory/settings.json）")
    t = team.add_parser("audit", help="核对子 Agent 实际使用的模型")
    t.add_argument("--json", action="store_true")
    t.add_argument("--limit", type=int, default=20)

    p = subparsers.add_parser("history", help="查看执行历史")
    p.add_argument("--task-id", help="任务 ID（可选）")
    p.add_argument("--limit", type=int, default=10, help="显示数量限制")

    p = subparsers.add_parser("acceptance", help="列出验收条件；--template 生成验收证据框架")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--template", action="store_true",
                   help="在任务板目录写入 acceptance-<任务ID>.json，结论和证据待填写")
    p.add_argument("--force", action="store_true", help="与 --template 一起使用：覆盖已有的证据文件")

    p = subparsers.add_parser("preflight", help="用无敏感数据的探针验证原生沙箱；失败时禁止受管派发")
    p.add_argument("--dispatcher", required=True, help="用户选定的调度模型完整 ID")
    p = subparsers.add_parser("run", help="受管派发（任务写了 role）：固定模型、自动记录、结束后保留成果待验收")
    p.add_argument("task_id")
    p.add_argument("--dispatcher", required=True)
    p.add_argument("--timeout", type=int, default=1800)

    p = subparsers.add_parser("execution", help="执行记录与中断恢复")
    execution = p.add_subparsers(dest="action", required=True)
    actions = {
        "begin": "登记开始并记录文件基线",
        "finish": "登记执行结束及结果",
        "inspect": "对比开始前后的文件变化和范围外改动",
        "audit": "核对子 Agent 实际使用的模型",
        "accept": "记录逐项验收证据",
        "retry": "记录检查结论，任务回到 PENDING 等待续做",
        "pause": "用户叫停：任务回到 PENDING，不计失败次数",
        "block": "记录检查结论并把任务改为 BLOCKED",
        "unblock": "按用户的决定解除 BLOCKED",
        "track": "登记执行期间启动、之后还在运行的进程",
    }
    for action, summary in actions.items():
        item = execution.add_parser(action, help=summary)
        item.add_argument("id", help="任务 ID" if action == "begin" else
                          "任务 ID（使用该任务当前的执行记录）或 execution_id")
        if action == "finish":
            item.add_argument("--outcome", required=True,
                              choices=["completed", "returned", "permission_rejected", "failed", "interrupted"],
                              help="当前会话直接执行的任务用 completed；派发的任务用 returned 等派发结果")
            item.add_argument("--ended-at", help="实际结束时间，带时区；中断且未知时省略")
        elif action == "accept":
            item.add_argument("--evidence-file", required=True, help="逐项验收 JSON")
        elif action in {"retry", "block", "unblock", "pause"}:
            item.add_argument("--reason", required=True,
                              help={"unblock": "用户的处理结果", "pause": "用户为什么叫停，以及已经做完的部分"}.get(
                                  action, "实际文件检查结果及续做范围"))
        elif action == "track":
            item.add_argument("--pid", type=int, required=True, help="进程的 PID")
            item.add_argument("--label", required=True, help="这个进程是什么，例如“dev server，端口 5173”")
    execution.add_parser("recover", help="列出尚未集成的执行记录，用于中断后恢复")
    execution.add_parser("sync", help="按任务板修复 checkpoint 里的任务进度")
    p = subparsers.add_parser("delivery", help="检查提交是否包含显式声明的运行依赖")
    p.add_argument("--commit", default="HEAD")
    p.add_argument("--paths", nargs="+", required=True)

    p = subparsers.add_parser("web", help="Web 看板：是否在运行和它的地址；start 启动，stop 关闭")
    p.add_argument("action", nargs="?", choices=["status", "start", "stop"], default="status", help="操作，默认 status")
    p.add_argument("--port", type=int, help="start 时使用的端口（默认从 5001 起找空闲端口）")
    p.add_argument("--json", action="store_true", help="JSON 输出")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        args.root = resolve_root(args.command)
        cmd_func = {
            "init": cmd_init,
            "doctor": cmd_doctor,
            "select": cmd_select,
            "status": cmd_status,
            "add": cmd_add,
            "show": cmd_show,
            "plan-execution": cmd_plan_execution,
            "batch": cmd_batch,
            "validate": cmd_validate,
            "update": cmd_update_status,
            "fail": cmd_fail,
            "integrate": cmd_integrate,
            "checkpoint": cmd_checkpoint,
            "config": cmd_config,
            "models": cmd_models,
            "team": cmd_team,
            "history": cmd_history,
            "acceptance": cmd_acceptance,
            "preflight": cmd_preflight,
            "run": cmd_run,
            "execution": cmd_execution,
            "delivery": cmd_delivery,
            "web": cmd_web,
        }[args.command]

        cmd_func(args)
    except OSError as e:
        target = f"{e.filename}: " if e.filename else ""
        print(f"错误: {target}{describe_error(e)}", file=sys.stderr)
        sys.exit(1)
    except (TaskStoreError, TeamError, ValueError, subprocess.TimeoutExpired) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
