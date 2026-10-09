"""Local preflight, manual acceptance and plain-text monitoring."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from platform_utils import FileLock, is_process_running
from tasks_store import (CliError, atomic_write, find_task, read_tasks_document,
                         resolve_task_paths, write_tasks_document)
from run_store import read_run_record, write_run_record


def task_definition(task_num, task_file):
    paths = resolve_task_paths(task_file)
    if not paths.json_path.exists() and not paths.markdown_path.exists():
        return {}
    return find_task(read_tasks_document(task_file, migrate=False), task_num) or {}


def check_dependencies(task, workdir):
    """Inspect distributions in the selected Python interpreter; never install packages."""
    deps = task.get('runtime_dependencies', {})
    if not isinstance(deps, dict):
        raise CliError('runtime_dependencies 必须是对象，任务依赖仍使用 dependencies')
    for kind in ('python', 'system'):
        if not isinstance(deps.get(kind, []), list) or any(not isinstance(x, str) or not x.strip() for x in deps.get(kind, [])):
            raise CliError(f'runtime_dependencies.{kind} 必须是字符串数组')
    python = deps.get('python_executable') or sys.executable
    if not isinstance(python, str):
        raise CliError('runtime_dependencies.python_executable 必须是字符串')
    if '/' in python or '\\' in python:
        python = str((Path(workdir) / python).resolve())
    missing = []
    if deps.get('python'):
        try:
            from packaging.requirements import Requirement, InvalidRequirement
        except ImportError as exc:
            raise CliError('检查 Python 版本约束需要 packaging，请先安装项目依赖') from exc
        for spec in deps['python']:
            try:
                requirement = Requirement(spec)
            except InvalidRequirement as exc:
                raise CliError(f'无效 Python 依赖: {spec}') from exc
            if requirement.url or requirement.extras or requirement.marker:
                raise CliError('预检仅支持包名与版本约束；extras、URL 和环境标记请在环境配置中处理')
            try:
                code = 'import importlib.metadata,sys; print(importlib.metadata.version(sys.argv[1]))'
                result = subprocess.run([python, '-c', code, requirement.name], cwd=workdir,
                                        capture_output=True, text=True, timeout=15)
                version = result.stdout.strip()
                if result.returncode or not requirement.specifier.contains(version, prereleases=True):
                    missing.append(spec)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                missing.append(spec + f' (无法通过 {python} 检查)')
    missing.extend(command for command in deps.get('system', []) if not shutil.which(command))
    return {'missing': missing, 'python_executable': python, 'checked': deps}


def preflight(task_num, workdir, task_file='planning/codex-tasks.md'):
    report = check_dependencies(task_definition(task_num, task_file), workdir)
    if report['missing']:
        print('WARNING: 缺少运行依赖: ' + ', '.join(report['missing']) +
              '；请在指定运行环境预装后继续（不会自动安装）。', file=sys.stderr)
    return report


def acceptance_items(task):
    lines = []
    for section in task.get('sections', []):
        if section['heading'] == '验收标准':
            for line in section['body'].splitlines():
                line = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\[[ xX]\]\s*)?', '', line).strip()
                if line:
                    lines.append(line)
    return lines


def verify_manual(args):
    import session_backend as session
    from task_board import task_fingerprint, run_identity
    task_num = session.task_id(args.task_num)
    document = read_tasks_document(args.task_file, migrate=False)
    task = find_task(document, task_num)
    if not task:
        raise CliError('任务板中没有此任务')
    items = acceptance_items(task)
    if not items:
        raise CliError('任务没有验收标准，不能手动通过')
    if args.list:
        print(json.dumps([{'id': i, 'criterion': item} for i, item in enumerate(items, 1)], ensure_ascii=False, indent=2))
        return 0
    if not args.note or not args.note.strip():
        raise CliError('手动验收必须提供 --note 记录实际测试证据')
    run = read_run_record(task_num)
    if run.get('status') not in ('success', 'blocked'):
        raise CliError('只有已结束的 success / blocked 执行可以手动验收')
    expected_run = run_identity(run)
    confirmed = set(args.confirm or [])
    valid = set(range(1, len(items) + 1))
    if confirmed - valid:
        raise CliError('存在无效的 --confirm 标准编号')
    for i, item in enumerate(items, 1):
        if i not in confirmed:
            if not sys.stdin.isatty():
                raise CliError(f'尚未确认标准 {i}: {item}；先 --list，再逐项传 --confirm 编号')
            if input(f'{i}. {item}\n已实际验证通过？[y/N] ').strip().lower() != 'y':
                raise CliError('验收未全部通过，未修改任务')
            confirmed.add(i)
    paths = resolve_task_paths(args.task_file)
    with session.lock(task_num), FileLock(paths.json_path.with_suffix('.json.lock')):
        latest = read_run_record(task_num)
        current_doc = read_tasks_document(args.task_file)
        current = find_task(current_doc, task_num)
        if (current != task or run_identity(latest) != expected_run or latest.get('status') != run.get('status')
                or is_process_running(int(latest.get('pid') or 0))):
            raise CliError('任务定义或执行发生变化，或进程仍在运行，请重新确认')
        report_path = (Path('.dual-ai-collab/manual-reports') / (uuid4().hex + '.json')).resolve()
        report = dict(passed=True, method='manual', note=args.note, verified_at=session.now(),
                      run_id=expected_run, task_fingerprint=task_fingerprint(task),
                      source_status=run['status'], workdir=run.get('workdir'),
                      criteria=[{'id': i, 'criterion': item, 'confirmed': True} for i, item in enumerate(items, 1)])
        atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        verification = {key: report[key] for key in ('passed', 'method', 'run_id', 'task_fingerprint')}
        verification['report_file'] = str(report_path)
        if latest.get('backend') == 'app-server':
            session.save(latest, verification=verification)
        else:
            latest['verification'] = verification
            write_run_record(latest)
        current.update(status='AWAITING_REVIEW', status_explicit=True)
        current.pop('review', None)
        current.pop('integration', None)
        write_tasks_document(current_doc, args.task_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def watch(task_num, interval=5):
    import session_backend as session
    from run_task import get_backend
    task_num = session.task_id(task_num)
    interval = session.number(interval, 'interval')
    try:
        while True:
            record = read_run_record(task_num)
            if not record:
                raise CliError('未找到运行记录')
            record = get_backend(record.get('backend', 'direct')).call('status', record)
            latest_event = ''
            if record.get('events_file'):
                try:
                    with open(record['events_file'], 'rb') as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - 16384))
                        for line in reversed(stream.read().decode('utf-8', errors='replace').splitlines()):
                            try:
                                event = json.loads(line)
                                latest_event = event.get('method', '')
                                break
                            except (ValueError, AttributeError):
                                continue
                except OSError:
                    pass
            print(f"#{task_num} status={record['status']} turn={record.get('turn_id') or '-'} "
                  f"最近事件={latest_event or '-'} 原因={record.get('error') or '-'}", flush=True)
            if record['status'] in session.TERMINAL:
                return 0 if record['status'] == 'success' else 1
            time.sleep(interval)
    except KeyboardInterrupt:
        return 130
