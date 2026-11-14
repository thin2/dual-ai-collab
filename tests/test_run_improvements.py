from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skill/scripts'))
import session_backend
from tasks_store import write_tasks_document, read_tasks_document, CliError
from run_store import read_run_record
from task_board import review_task, projection
from run_support import check_dependencies, verify_manual, preflight
from run_diagnostics import turn_timeout, classify_blocked
from task_history import record_task_start, record_task_end, get_task_statistics, generate_report


def cli(project, *args):
    return subprocess.run([sys.executable, str(ROOT / 'skill/scripts/cli.py'), *args],
                          cwd=project, capture_output=True, text=True, timeout=10)


@pytest.fixture
def blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_tasks_document({'tasks': [dict(id='001', title='API', priority='P1', status='IN_PROGRESS', sections=[
        dict(heading='验收标准', body='- [ ] API returns 200\n- [ ] Invalid requests return 400')])]})
    directory = tmp_path / '.dual-ai-collab/sessions/test'
    directory.mkdir(parents=True)
    session_backend.save(dict(task_num='001', run_id='r1', backend='app-server', status='blocked', pid=0,
                             workdir=str(tmp_path), run_dir=str(directory),
                             started_at='2026-10-09T00:00:00+00:00', finished_at='2026-10-09T00:00:05+00:00',
                             blocked_reason='No module named flask', error='No module named flask'))
    return tmp_path


def test_manual_acceptance_requires_every_criterion_then_force_review(blocked):
    listed = cli(blocked, 'run', 'verify-manual', '1', '--list')
    assert len(json.loads(listed.stdout)) == 2
    before = Path('planning/tasks.json').read_bytes()
    result = cli(blocked, 'run', 'verify-manual', '1', '--note', 'HTTP tests passed', '--confirm', '1')
    assert result.returncode == 1 and '--confirm' in result.stderr
    assert Path('planning/tasks.json').read_bytes() == before
    assert cli(blocked, 'board', 'review', '1', '--decision', 'approved', '--note', 'review', '--force').returncode == 1
    result = cli(blocked, 'run', 'verify-manual', '1', '--note', 'HTTP tests passed', '--confirm', '1', '--confirm', '2')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['source_status'] == 'blocked'
    assert read_run_record('001')['status'] == 'blocked'
    assert read_tasks_document()['tasks'][0]['status'] == 'AWAITING_REVIEW'
    assert cli(blocked, 'board', 'review', '1', '--decision', 'approved', '--note', 'review').returncode == 1
    result = cli(blocked, 'board', 'review', '1', '--decision', 'approved', '--note', 'review', '--force')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['forced'] is True
    doc = read_tasks_document()
    doc['tasks'][0]['sections'][0]['body'] += '\n- New criterion'
    write_tasks_document(doc)
    assert cli(blocked, 'board', 'review', '1', '--decision', 'approved', '--note', 'review', '--force').returncode == 1


def test_manual_rejects_running_and_invalid_confirmation(blocked):
    opts = SimpleNamespace(task_num='001', task_file='planning/tasks.json', list=False, note='test', confirm=[99])
    with pytest.raises(CliError, match='无效'):
        verify_manual(opts)
    opts.confirm = [1, 2]
    record = read_run_record('001')
    record['status'] = 'running'
    session_backend.save(record)
    with pytest.raises(CliError, match='已结束'):
        verify_manual(opts)


def test_watch_terminal_and_partial_event_line(blocked):
    record = read_run_record('001')
    event_file = blocked / 'events.jsonl'
    event_file.write_text('{"method": "turn/completed"}\n{"method":')
    session_backend.save(record, events_file=str(event_file))
    result = cli(blocked, 'run', 'watch', '1', '--interval', '.01')
    assert result.returncode == 1 and 'status=blocked' in result.stdout
    assert 'turn/completed' in result.stdout and 'No module named flask' in result.stdout
    assert 'Traceback' not in result.stderr
    assert cli(blocked, 'run', 'watch', '1', '--interval', 'nan').returncode == 1
    assert cli(blocked, 'run', 'watch', '999').returncode == 1


def test_verbose_board_and_blocked_history(blocked):
    result = cli(blocked, 'board', 'show', '--verbose')
    assert result.returncode == 0, result.stderr
    assert '5.0 秒' in result.stdout and 'No module named flask' in result.stdout
    assert 'run verify-manual 001 --list' in result.stdout
    execution = record_task_start('001')
    record_task_end(execution, 'blocked', 1, 'No module named flask',
                    blocked_reason='No module named flask', blocked_category='dependency_missing')
    stats = get_task_statistics('001')
    assert stats['blocked_categories'] == {'dependency_missing': 1}
    assert 'No module named flask' in generate_report()


def test_dependency_check_versions_missing_and_separate_task_dependencies(blocked, capsys):
    task = {'dependencies': '#002', 'runtime_dependencies': {
        'python': ['pytest>=1', 'pytest>99999', 'nonexistent-dual-ai-fixture'],
        'system': ['nonexistent-dual-ai-command']}}
    result = check_dependencies(task, blocked)
    assert result['missing'] == ['pytest>99999', 'nonexistent-dual-ai-fixture', 'nonexistent-dual-ai-command']
    doc = read_tasks_document()
    doc['tasks'][0]['runtime_dependencies'] = task['runtime_dependencies']
    write_tasks_document(doc)
    preflight('001', str(blocked))
    assert 'WARNING' in capsys.readouterr().err
    assert read_tasks_document()['tasks'][0]['dependencies'] == '无'
    with pytest.raises(CliError):
        check_dependencies({'runtime_dependencies': {'python': 'flask'}}, blocked)


@pytest.mark.skipif(sys.platform == 'win32', reason='虚拟环境的解释器只在 POSIX 上是符号链接')
def test_dependency_check_sees_packages_installed_in_a_virtual_environment(tmp_path):
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(tmp_path / 'venv')],
                   check=True, capture_output=True, timeout=60)
    python = tmp_path / 'venv/bin/python'
    assert python.is_symlink()
    site_packages = subprocess.run([str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                                   check=True, capture_output=True, text=True, timeout=15).stdout.strip()
    metadata = Path(site_packages) / 'dual_ai_fixture-1.2.3.dist-info/METADATA'
    metadata.parent.mkdir(parents=True)
    metadata.write_text('Metadata-Version: 2.1\nName: dual-ai-fixture\nVersion: 1.2.3\n')
    for executable in ('venv/bin/python', str(python)):
        task = {'runtime_dependencies': {'python': ['dual-ai-fixture>=1', 'dual-ai-fixture>2'],
                                         'python_executable': executable}}
        result = check_dependencies(task, tmp_path)
        assert result['missing'] == ['dual-ai-fixture>2']
        assert Path(result['python_executable']) == tmp_path.resolve() / 'venv/bin/python'


def test_priority_timeout_precedence(blocked):
    assert turn_timeout('001', {}, {}) == 1200
    assert turn_timeout('001', {}, {'app_server_priority_timeouts': {'P1': 42}}) == 42
    assert turn_timeout('001', {}, {'app_server_turn_timeout': 55}) == 55
    assert turn_timeout('001', {'timeout': 7}, {'app_server_turn_timeout': 55}) == 7
    with pytest.raises(CliError):
        turn_timeout('001', {'timeout': 0}, {})


@pytest.mark.parametrize('reason,expected', [('No module named flask', 'dependency_missing'),
    ('sandbox network denied', 'sandbox_restriction'), ('Permission denied', 'permission_denied'),
    ('timed out', 'timeout'), ('unspecified', 'unknown')])
def test_blocked_reason_classification(reason, expected):
    assert classify_blocked(reason) == expected
