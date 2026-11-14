from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skill/scripts'))
import session_backend
from tasks_store import CliError, write_tasks_document, read_tasks_document
from run_store import read_run_record
from verify_task import verify_report


def cli(project, *args):
    return subprocess.run([sys.executable, str(ROOT / 'skill/scripts/cli.py'), 'run', *args],
                          cwd=project, text=True, capture_output=True, timeout=15)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = (ROOT / 'tests/fixtures/fake_app_server.py').read_text()
    stub = tmp_path / 'fake-codex'
    stub.write_text('#!' + sys.executable + '\n' + '\n'.join(fixture.splitlines()[1:]))
    stub.chmod(0o755)
    monkeypatch.setenv('CODEX_BIN', str(stub))
    yield tmp_path
    for state in (tmp_path / '.dual-ai-collab/sessions').glob('*/state.json'):
        record = json.loads(state.read_text())
        if record['status'] in session_backend.ACTIVE and record.get('pid'):
            try:
                os.kill(record['pid'], 15)
            except OSError:
                pass


def wait(task='001', predicate=lambda r: r['status'] in session_backend.TERMINAL):
    deadline = time.monotonic() + 12
    record = {}
    while time.monotonic() < deadline:
        record = read_run_record(task)
        if record and predicate(record):
            if record['status'] in session_backend.TERMINAL:
                # The worker writes terminal state just before exiting.
                from platform_utils import is_process_running
                if is_process_running(record['pid']):
                    time.sleep(.05)
                    continue
            return record
        time.sleep(.05)
    raise AssertionError(record)


def board():
    command = f'''"{sys.executable}" -c "from pathlib import Path; assert Path('artifact.txt').read_text() == 'good'"'''
    write_tasks_document({'tasks': [{'id': '001', 'status': 'OPEN', 'sections': [
        {'heading': '验收标准', 'body': f'`{command}`'}]}]})


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_execute_verify_repair_resumes_same_thread(project):
    board()
    result = cli(project, 'start', '1', 'implement', '--backend', 'app-server')
    assert result.returncode == 0, result.stderr
    first = wait()
    assert first['status'] == 'success', first
    assert cli(project, 'start', '001', 'again', '--backend', 'app-server').returncode == 1
    result = cli(project, 'complete', '001', '--repair')
    assert result.returncode == 1, result.stderr
    repair = json.loads(result.stdout)['repair_run']
    second = wait()
    assert second['run_id'] == repair['run_id'] != first['run_id']
    assert second['thread_id'] == first['thread_id']
    assert second['turn_id'] != first['turn_id']
    assert Path(second['workdir'], 'artifact.txt').read_text() == 'good'
    assert read_tasks_document()['tasks'][0]['status'] == 'OPEN'
    result = cli(project, 'complete', '001')
    assert result.returncode == 0, result.stderr
    assert read_tasks_document()['tasks'][0]['status'] == 'AWAITING_REVIEW'
    report = json.loads(Path(json.loads(result.stdout)['report_file']).read_text())
    assert report['passed'] and report['thread_id'] == first['thread_id']
    assert Path(first['run_dir'], 'state.json').exists()
    events = json.loads(cli(project, 'events', '001').stdout)
    assert any(event.get('method') == 'turn/completed' for event in events['events'])
    assert session_backend.events('001', events['next_after'])['events'] == []


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_steer_interrupt_and_duplicate_start(project):
    assert cli(project, 'start', '001', 'WAIT', '--backend', 'app-server').returncode == 0
    running = wait(predicate=lambda r: bool(r.get('turn_id')))
    assert cli(project, 'start', '1', 'duplicate', '--backend', 'direct').returncode == 1
    assert cli(project, 'steer', '001', 'focus on tests').returncode == 0
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not Path('steered.txt').exists():
        time.sleep(.05)
    assert Path('steered.txt').read_text() == 'focus on tests'
    assert cli(project, 'stop', '001').returncode == 0
    stopped = wait()
    assert stopped['status'] == 'stopped', stopped
    assert cli(project, 'continue', '001', '修复').returncode == 0
    assert wait()['thread_id'] == running['thread_id']


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
@pytest.mark.parametrize('prompt,expected', [('DISCONNECT', 'failed'), ('APPROVAL', 'blocked'), ('WAIT', 'blocked')])
def test_failure_modes_do_not_report_success(project, prompt, expected):
    assert cli(project, 'start', '001', prompt, '--backend', 'app-server', '--timeout', '0.5').returncode == 0
    record = wait()
    assert record['status'] == expected, record
    if prompt == 'WAIT':
        assert record['blocked_category'] == 'timeout'
        history = json.loads(Path('.dual-ai-collab/history', record['history_id'] + '.json').read_text())
        assert history['blocked_category'] == 'timeout' and history['blocked_reason']
    assert cli(project, 'complete', '001').returncode == 1


def test_unsupported_capability_and_missing_commands(project):
    result = cli(project, 'capabilities')
    caps = json.loads(result.stdout)
    assert caps['app-server']['continue'] and not caps['direct']['continue']
    assert not any(caps['plugin'].values())
    assert verify_report([], str(project))['passed'] is False


def test_dead_worker_reconciled_without_replaying(project):
    run_dir = project / 'run'
    run_dir.mkdir()
    session_backend.save({'task_num': '001', 'backend': 'app-server', 'run_dir': str(run_dir),
                          'pid': 0, 'status': 'running', 'thread_id': 'saved-thread'})
    record = session_backend.status(read_run_record('001'))
    assert record['status'] == 'interrupted'
    assert record['thread_id'] == 'saved-thread'


def test_verification_timeout_is_failure(project):
    result = verify_report([f'"{sys.executable}" -c "import time; time.sleep(30)"'], str(project), timeout=.2)
    assert not result['passed']
    assert result['commands'][0]['timed_out']


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_isolated_worktree_and_root_owned_records(project, tmp_path):
    repo = tmp_path / 'code'
    repo.mkdir()
    def git(*args):
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
    git('init')
    (repo / 'README.md').write_text('fixture')
    git('add', 'README.md')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    board()
    result = cli(project, 'start', '001', '修复', '--backend', 'app-server', '--workdir', str(repo), '--isolate')
    assert result.returncode == 0, result.stderr
    record = wait()
    assert record['status'] == 'success', record
    assert record['isolated'] and record['workdir'] != str(repo)
    assert not (repo / 'artifact.txt').exists()
    assert cli(project, 'complete', '001').returncode == 0
    assert read_tasks_document()['tasks'][0]['status'] == 'AWAITING_REVIEW'
    assert not (Path(record['workdir']) / '.dual-ai-collab/runs').exists()
    from task_board import review_task, integrate_task
    from tasks_store import executable_tasks
    from types import SimpleNamespace
    doc = read_tasks_document()
    doc['tasks'].append(dict(id='002', title='dependent', status='OPEN', dependencies='#001'))
    write_tasks_document(doc)
    assert executable_tasks(read_tasks_document()) == []
    options = SimpleNamespace(task_num='001', task_file='planning/tasks.json',
                              decision='approved', note='Reviewed isolated implementation',
                              target=str(repo), commit='HEAD')
    review_task(options)
    assert executable_tasks(read_tasks_document()) == []
    # Simulate a reviewer integrating only the task artifact (not worker runtime files).
    (repo / 'artifact.txt').write_text(Path(record['workdir'], 'artifact.txt').read_text())
    git('add', 'artifact.txt')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'integrate feature')
    integrate_task(options)
    assert [task['id'] for task in executable_tasks(read_tasks_document())] == ['002']
    assert cli(project, 'continue', '001', '修复').returncode == 0
    wait()
    assert executable_tasks(read_tasks_document()) == []



def test_worktree_refuses_dirty_source(project):
    from task_workspace import create_worktree
    subprocess.run(['git', 'init'], cwd=project, check=True, capture_output=True)
    with pytest.raises(CliError, match='干净'):
        create_worktree(project, project / 'wt')


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_concurrent_start_only_one_worker(project):
    args = [sys.executable, str(ROOT / 'skill/scripts/cli.py'), 'run', 'start', '001', 'WAIT', '--backend', 'app-server']
    procs = [subprocess.Popen(args, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [proc.communicate(timeout=15) for proc in procs]
    assert sorted(proc.returncode for proc in procs) == [0, 1], results
    wait(predicate=lambda r: bool(r.get('turn_id')))
    assert len(list((project / '.dual-ai-collab/sessions').iterdir())) == 1
    assert cli(project, 'stop', '001').returncode == 0
    assert wait()['status'] == 'stopped'


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_missing_resume_thread_never_starts_new_one(project):
    assert cli(project, 'start', '001', 'first', '--backend', 'app-server').returncode == 0
    first = wait()
    (project / '.fake-sessions.json').write_text('[]')
    assert cli(project, 'continue', '001', '修复').returncode == 0
    second = wait()
    assert second['status'] == 'failed'
    assert second['thread_id'] == first['thread_id']
    assert json.loads((project / '.fake-sessions.json').read_text()) == []


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_missing_acceptance_cannot_complete_or_repair(project):
    write_tasks_document({'tasks': [{'id': '001', 'status': 'OPEN'}]})
    assert cli(project, 'start', '001', 'first', '--backend', 'app-server').returncode == 0
    wait()
    result = cli(project, 'complete', '001', '--repair')
    assert result.returncode == 1
    assert 'repair_run' not in json.loads(result.stdout)
    assert read_tasks_document()['tasks'][0]['status'] == 'OPEN'


def test_protocol_error_and_request_timeout(project):
    from app_server_client import AppServerClient
    for script, pattern in [('print("invalid", flush=True)', '协议输出'),
                            ('import time; time.sleep(30)', '超时')]:
        with open(project / 'server.log', 'w') as log:
            client = AppServerClient([sys.executable, '-c', script], cwd=project, stderr=log, timeout=.15)
            try:
                with pytest.raises(CliError, match=pattern):
                    client.initialize()
            finally:
                client.close()
            assert client.process.poll() is not None


def test_live_lock_is_not_stolen_and_dead_lock_recovers(project, monkeypatch):
    from platform_utils import FileLock
    import platform_utils
    path = project / 'lock'
    path.write_text(str(os.getpid()))
    assert not FileLock(path, stale_after=0)._is_stale()
    monkeypatch.setattr(platform_utils, 'is_process_running', lambda pid: False)
    assert FileLock(path, stale_after=3600)._is_stale()


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_continue_reconciles_abandoned_history_without_status_query(project):
    from task_history import record_task_start, get_task_history
    assert cli(project, 'start', '001', 'first', '--backend', 'app-server').returncode == 0
    previous = wait()
    history_id = record_task_start('001', adapter='app-server')
    session_backend.save(previous, status='running', pid=0, history_id=history_id)
    assert cli(project, 'continue', '001', '修复').returncode == 0
    current = wait()
    assert current['thread_id'] == previous['thread_id']
    assert json.loads(Path(previous['run_dir'], 'state.json').read_text())['status'] == 'interrupted'
    old_history = json.loads((project / '.dual-ai-collab/history' / (history_id + '.json')).read_text())
    assert old_history['status'] == 'failed'


@pytest.mark.skipif(os.name == 'nt', reason='executable Python fixture')
def test_context_is_refreshed_per_turn(project):
    board()
    result = cli(project, 'start', '001', '修复', '--backend', 'app-server',
                 '--context-task-file', 'planning/tasks.json')
    assert result.returncode == 0, result.stderr
    first = wait()
    first_context = Path(first['context_file']).read_text()
    doc = read_tasks_document()
    doc['tasks'][0]['sections'].append({'heading': '决策', 'body': 'Keep public API stable'})
    write_tasks_document(doc)
    result = cli(project, 'continue', '001', '继续修复')
    assert result.returncode == 0, result.stderr
    second = wait()
    assert first['thread_id'] == second['thread_id']
    assert second['run_id'] != first['run_id']
    assert 'Keep public API stable' in Path(second['context_file']).read_text()
    assert Path(first['context_file']).read_text() == first_context
    assert 'Keep public API stable' in Path(second['prompt_file']).read_text()
