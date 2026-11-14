"""Diagnostics are recorded evidence; text classification is only a best-effort hint."""
from __future__ import annotations

from datetime import datetime, timezone
import shlex
from pathlib import Path


def classify_blocked(reason):
    text = (reason or '').lower()
    for category, terms in (
        ('dependency_missing', ('modulenotfounderror', 'no module named', '依赖缺失', '未安装', 'not installed')),
        ('sandbox_restriction', ('sandbox', '沙箱', 'network is unreachable', '网络不可用')),
        ('permission_denied', ('permission denied', '权限拒绝', 'operation not permitted')),
        ('timeout', ('超时', 'timed out', 'timeout')),
    ):
        if any(term in text for term in terms):
            return category
    return 'unknown'


def turn_timeout(task_num, options, config, previous=None):
    from run_support import task_definition
    from session_backend import number
    if options.get('timeout') is not None:
        return number(options['timeout'], 'timeout')
    if 'app_server_turn_timeout' in config:
        return number(config['app_server_turn_timeout'], 'app_server_turn_timeout')
    task_file = (previous or {}).get('context_task_file') or options.get('context_task_file') or 'planning/codex-tasks.md'
    priority = task_definition(task_num, task_file).get('priority', 'P2')
    defaults = {'P0': 1800, 'P1': 1200, 'P2': 600, 'P3': 300}
    configured = config.get('app_server_priority_timeouts', {})
    if not isinstance(configured, dict):
        from tasks_store import CliError
        raise CliError('app_server_priority_timeouts 必须是对象')
    return number(configured.get(priority, defaults.get(priority, 600)), 'priority timeout')


def duration_seconds(run):
    try:
        start = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(run['finished_at'].replace('Z', '+00:00')) if run.get('finished_at') else datetime.now(timezone.utc)
        return round(max(0, (end - start).total_seconds()), 1)
    except (KeyError, ValueError, TypeError):
        return None


def next_command(task, run, review, verification, integrated, task_file="planning/codex-tasks.md"):
    cli = 'python3 ' + shlex.quote(str(Path(__file__).with_name('cli.py').resolve()))
    task_id = shlex.quote(str(task['id']))
    board_file = shlex.quote(str(task_file))
    flag = ' --task-file ' + board_file
    if integrated:
        return cli + ' select ' + board_file
    if review == 'rejected':
        return cli + f' run continue {task_id} "按审查意见修复"'
    if review == 'approved':
        target = shlex.quote(str(run.get('source_workdir') or run.get('workdir') or '/path/to/source'))
        return cli + f' board integrate {task_id} --target {target} --commit COMMIT_SHA --note "集成说明"' + flag
    if verification == 'passed':
        force = ' --force' if run.get('status') == 'blocked' else ''
        return cli + f' board review {task_id} --decision approved --note "审查结论"{force}' + flag
    if run.get('status') == 'blocked':
        return cli + f' run verify-manual {task_id} --list' + flag
    if run.get('status') in ('running', 'starting', 'stopping'):
        return cli + f' run watch {task_id}'
    if run.get('status') == 'success':
        action = 'run complete' if run.get('backend') == 'app-server' else 'verify run'
        suffix = flag if run.get('backend') == 'app-server' else ' ' + board_file + ' --workdir ' + shlex.quote(str(run.get('workdir') or '.'))
        return cli + f' {action} {task_id}' + suffix
    if run.get('status') in ('failed', 'interrupted', 'stopped'):
        return cli + f' run status {task_id}'
    return cli + ' select ' + board_file
