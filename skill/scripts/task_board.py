"""Task board projection, review receipts, integration checks and bounded context packs."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from platform_utils import FileLock, is_process_running
from tasks_store import (CliError, atomic_write, read_tasks_document, write_tasks_document,
                         find_task, resolve_task_paths, dependency_ids, dependency_satisfied)
from run_store import read_run_record


def canonical(value):
    from session_backend import task_id
    return task_id(value)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def task_fingerprint(task):
    # Scheduling and display fields do not define the implementation contract.
    contract = {key: task.get(key) for key in ('id', 'title', 'dependencies', 'sections', 'extra_fields', 'runtime_dependencies')}
    return hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def current_run(task, project_root=None):
    return read_run_record(canonical(task['id']), project_root=project_root)


def run_identity(run):
    if not run:
        return None
    return run.get('run_id') or hashlib.sha256(json.dumps(
        {key: run.get(key) for key in ('backend', 'started_at', 'pid', 'prompt_file')},
        sort_keys=True).encode()).hexdigest()


def receipt_valid(task, receipt, run=None):
    run = current_run(task) if run is None else run
    return bool(receipt and receipt.get('task_fingerprint') == task_fingerprint(task)
                and receipt.get('run_id') == run_identity(run))


def integration_valid(task, run=None):
    receipt = task.get('integration', {})
    if task.get('status') != 'DONE' or not receipt_valid(task, receipt, run):
        return False
    review = task.get('review', {})
    if review.get('decision') != 'approved' or not receipt_valid(task, review, run):
        return False
    if not receipt.get('commit') or not receipt.get('target') or not receipt.get('report_file'):
        return False
    from task_workspace import git
    try:
        git(receipt['target'], 'merge-base', '--is-ancestor', receipt['commit'], 'HEAD')
        report = json.loads(Path(receipt['report_file']).read_text())
        if not isinstance(report, dict) or not report.get('target_head'):
            return False
        git(receipt['target'], 'merge-base', '--is-ancestor', report['target_head'], 'HEAD')
        return (report.get('passed') is True and report.get('commit') == receipt['commit']
                and report.get('target') == receipt['target'])
    except (CliError, OSError, ValueError):
        return False


def projection(document, task_file="planning/codex-tasks.md", *, project_root=None):
    rows = []
    runs = {task["id"]: current_run(task, project_root) for task in document["tasks"]}
    integrated_tasks = {task["id"]: integration_valid(task, runs[task["id"]]) for task in document["tasks"]}
    for task in document['tasks']:
        run = runs[task["id"]]
        execution = run.get('status', 'not_started')
        if execution in ('starting', 'running', 'stopping', 'verifying') and not is_process_running(int(run.get('pid') or 0)):
            execution = 'interrupted'
        verification = run.get('verification', {})
        verified = receipt_valid(task, verification, run) if 'run_id' in verification else (
            verification.get('task_fingerprint') == task_fingerprint(task))
        verification_state = ('passed' if verification.get('passed') else 'failed') if verified else 'unknown'
        review = task.get('review', {})
        review_state = review.get('decision', 'pending') if receipt_valid(task, review, run) else 'pending'
        integrated = integrated_tasks[task["id"]]
        waiting = [dep for dep in dependency_ids(task.get('dependencies'))
                   if not integrated_tasks.get((find_task(document, dep) or {}).get('id'), False)]
        if integrated:
            next_action = '已交付'
        elif execution in ('starting', 'running', 'stopping', 'verifying'):
            next_action = '等待执行；可查看 events'
        elif waiting:
            next_action = '等待依赖集成: ' + ', '.join(waiting)
        elif review_state == 'rejected':
            next_action = '按审查意见修复，再重新验收与审查'
        elif review_state == 'approved':
            next_action = '集成代码到目标仓库，再运行 board integrate'
        elif verification_state == 'passed':
            next_action = '审查代码并运行 board review'
        elif task['status'] in ('DONE', 'VERIFIED') and not run:
            next_action = '历史任务：审查并确认目标仓库集成'
        elif execution == 'success':
            next_action = '运行 run complete 验收（CLI 后端用 verify run）'
        elif execution in ('failed', 'blocked', 'interrupted', 'stopped') or review_state == 'rejected':
            next_action = '检查诊断后修复；会话后端使用 run continue'
        else:
            next_action = '开始执行'
        from run_diagnostics import duration_seconds, next_command
        rows.append(dict(duration_seconds=duration_seconds(run), blocked_reason=run.get('blocked_reason') or run.get('error'),
                         next_command=next_command(task, run, review_state, verification_state, integrated, task_file),
                         id=task['id'], title=task['title'], phase=task['status'], execution=execution,
                         verification=verification_state, review=review_state,
                         integration='confirmed' if integrated else 'unconfirmed',
                         blocked_by=waiting, next_action=next_action,
                         run_id=run.get('run_id'), thread_id=run.get('thread_id'),
                         workdir=run.get('workdir'), report_file=verification.get('report_file')))
    return rows


def context_pack(task_num, task_file='planning/codex-tasks.md'):
    document = read_tasks_document(task_file, migrate=False)
    task = find_task(document, task_num)
    if not task:
        raise CliError('任务板中没有此任务')
    deps = []
    for dep in dependency_ids(task['dependencies']):
        other = find_task(document, dep)
        deps.append({'id': dep, 'title': other.get('title') if other else None,
                     'integrated': bool(other and integration_valid(other))})
    # Include task/spec references, never recursively load arbitrary referenced files or logs.
    content = {'task_file': str(Path(task_file).resolve()), 'task_fingerprint': task_fingerprint(task),
               'project_context': document.get('header', ''),
               'task': {key: task.get(key) for key in ('id', 'title', 'sections', 'extra_fields', 'runtime_dependencies')},
               'dependencies': deps, 'acceptance_commands': task.get('acceptance_commands', [])}
    result = '# 任务上下文快照\n\n' + json.dumps(content, ensure_ascii=False, indent=2) + '\n'
    if len(result.encode('utf-8')) > 65536:
        raise CliError('任务上下文超过 64 KiB，请精简任务定义后重试')
    return result


def _task(document, task_num):
    task = find_task(document, task_num)
    if task is None:
        raise CliError('任务板中没有此任务')
    return task


def _idle(task):
    run = current_run(task)
    if run and (run.get('status') in ('starting', 'running', 'stopping', 'verifying')
                or is_process_running(int(run.get('pid') or 0))):
        raise CliError('任务仍在执行或需要 run status 恢复状态')
    return run


def review_task(args):
    from session_backend import lock
    paths = resolve_task_paths(args.task_file)
    with lock(canonical(args.task_num)), FileLock(paths.json_path.with_suffix('.json.lock')):
        document = read_tasks_document(args.task_file)
        task = _task(document, args.task_num)
        run = _idle(task)
        if args.decision == 'approved':
            forced_blocked = run.get('status') == 'blocked' and getattr(args, 'force', False)
            if run and run.get('status') != 'success' and not forced_blocked:
                raise CliError('当前执行尚未成功；blocked 任务需先 verify-manual 再 board review --force')
            if forced_blocked:
                verification = run.get('verification', {})
                if (not verification.get('passed') or verification.get('method') != 'manual'
                        or not receipt_valid(task, verification, run)):
                    raise CliError('--force 不代替验收；请先运行 run verify-manual 并逐项确认')
            if run.get('backend') == 'app-server':
                verification = run.get('verification', {})
                if not verification.get('passed') or verification.get('task_fingerprint') != task_fingerprint(task):
                    raise CliError('请先对当前任务运行 run complete 验收')
            elif not run and task['status'] not in ('DONE', 'VERIFIED', 'AWAITING_REVIEW'):
                raise CliError('任务尚未执行，不能通过审查')
        task['review'] = dict(decision=args.decision, note=args.note, recorded_at=timestamp(),
                              forced=bool(getattr(args, 'force', False)), source_status=run.get('status'),
                              run_id=run_identity(run), task_fingerprint=task_fingerprint(task))
        task.pop('integration', None)
        task['status'] = 'AWAITING_INTEGRATION' if args.decision == 'approved' else 'REJECTED'
        write_tasks_document(document, args.task_file)
        return task['review']


def integrate_task(args):
    """Attest an existing integration; never perform a merge or create a commit."""
    from session_backend import lock
    from task_workspace import git
    from verify_task import verify_report
    from config import load_config
    paths = resolve_task_paths(args.task_file)
    board_lock = paths.json_path.with_suffix('.json.lock')
    with lock(canonical(args.task_num)):
        with FileLock(board_lock):
            document = read_tasks_document(args.task_file)
            task = _task(document, args.task_num)
            run = _idle(task)
            review = task.get('review', {})
            if not receipt_valid(task, review, run) or review.get('decision') != 'approved':
                raise CliError('需要对当前任务和执行轮次完成审查')
            original = json.dumps(task, sort_keys=True)
        target = Path(args.target).resolve()
        if Path(git(target, 'rev-parse', '--show-toplevel')).resolve() != target:
            raise CliError('--target 必须是目标 Git 仓库根目录')
        if run.get('isolated') and target != Path(run['source_workdir']).resolve():
            raise CliError('隔离任务必须确认集成到原始仓库')
        if git(target, 'status', '--porcelain'):
            raise CliError('目标仓库必须干净且代码已提交')
        commit = git(target, 'rev-parse', '--verify', args.commit + '^{commit}')
        git(target, 'merge-base', '--is-ancestor', commit, 'HEAD')
        head = git(target, 'rev-parse', 'HEAD')
        report = verify_report(task['acceptance_commands'], str(target),
                               timeout=load_config().get('verification_timeout', 120))
        if git(target, 'rev-parse', 'HEAD') != head or git(target, 'status', '--porcelain'):
            report['passed'] = False
            report['reason'] = '集成验收期间目标仓库发生变化，未确认集成'
        report.update(commit=commit, target_head=head, target=str(target), verified_at=timestamp())
        report_path = (Path('.dual-ai-collab/integration-reports') / (uuid4().hex + '.json')).resolve()
        atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        if not report['passed']:
            with FileLock(board_lock):
                document = read_tasks_document(args.task_file)
                current = _task(document, args.task_num)
                if json.dumps(current, sort_keys=True) == original:
                    current.pop('integration', None)
                    current['status'] = 'AWAITING_INTEGRATION'
                    write_tasks_document(document, args.task_file)
            raise CliError(f'目标仓库验收未通过: {report_path}')
        with FileLock(board_lock):
            document = read_tasks_document(args.task_file)
            current = _task(document, args.task_num)
            if json.dumps(current, sort_keys=True) != original:
                raise CliError('集成验收期间任务定义变化，请重新审查')
            current['integration'] = dict(commit=commit, target=str(target), note=args.note,
                run_id=run_identity(run), task_fingerprint=task_fingerprint(task),
                report_file=str(report_path), recorded_at=timestamp())
            current['status'] = 'DONE'
            write_tasks_document(document, args.task_file)
            return current['integration']


def register_subparsers(subparsers):
    board = subparsers.add_parser('board', help='任务面板、上下文、审查与集成确认')
    commands = board.add_subparsers(dest='board_command', required=True)
    show = commands.add_parser('show')
    show.add_argument('--json', action='store_true')
    show.add_argument('--verbose', action='store_true', help='显示耗时、阻塞原因和下一步命令')
    context = commands.add_parser('context')
    context.add_argument('task_num')
    context.add_argument('--output', help='写出上下文文件，省略时输出到终端')
    review = commands.add_parser('review')
    review.add_argument('task_num')
    review.add_argument('--force', action='store_true', help='允许手动验收通过的 blocked 任务进入审查')
    review.add_argument('--decision', choices=('approved', 'rejected'), required=True)
    review.add_argument('--note', required=True, help='审查结论与证据')
    integrate = commands.add_parser('integrate')
    integrate.add_argument('task_num')
    integrate.add_argument('--target', required=True)
    integrate.add_argument('--commit', required=True)
    integrate.add_argument('--note', required=True, help='确认提交包含本任务改动的说明')
    for command in (show, context, review, integrate):
        command.add_argument('--task-file', default='planning/codex-tasks.md')


def dispatch(args):
    if args.board_command == 'show':
        rows = projection(read_tasks_document(args.task_file, migrate=False), args.task_file)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print('| 任务 | 阶段 | 执行 | 验收 | 审查 | 集成 | 下一步 |')
            print('| --- | --- | --- | --- | --- | --- | --- |')
            for row in rows:
                values = [f"#{row['id']} {row['title']}"] + [row[key] for key in
                    ('phase', 'execution', 'verification', 'review', 'integration', 'next_action')]
                print('| ' + ' | '.join(str(value).replace('|', '\\|').replace('\n', ' ') for value in values) + ' |')
            if args.verbose:
                for row in rows:
                    print(f"\n#{row['id']} 耗时: {row['duration_seconds']} 秒\n阻塞原因: {row['blocked_reason'] or '-'}\n下一步命令: {row['next_command']}")
    elif args.board_command == 'context':
        content = context_pack(args.task_num, args.task_file)
        if args.output:
            atomic_write(Path(args.output), content)
        else:
            print(content, end='')
    else:
        if not args.note.strip():
            raise CliError('审查/集成说明不能为空')
        result = review_task(args) if args.board_command == 'review' else integrate_task(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
