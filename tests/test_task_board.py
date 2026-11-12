from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skill/scripts'))
from tasks_store import read_tasks_document, write_tasks_document, executable_tasks, CliError
from task_board import (review_task, integrate_task, projection, context_pack,
                        integration_valid, task_fingerprint)
from run_store import write_run_record


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'source'
    target.mkdir()
    git(target, 'init', '-q')
    git(target, 'config', 'user.name', 'Test')
    git(target, 'config', 'user.email', 'test@example.com')
    (target / 'artifact.txt').write_text('good')
    git(target, 'add', '.')
    git(target, 'commit', '-qm', 'implementation')
    command = f'''"{sys.executable}" -c "from pathlib import Path; assert Path('artifact.txt').read_text() == 'good'"'''
    write_tasks_document({'tasks': [dict(id='001', title='Feature', status='DONE', sections=[
        dict(heading='任务描述', body='Add feature; preserve API'),
        dict(heading='验收标准', body=f'`{command}`')]),
        dict(id='002', title='Dependent', status='OPEN', dependencies='#001')]})
    return target


def args(project, **kwargs):
    return SimpleNamespace(task_num='001', task_file='planning/tasks.json', decision='approved',
                           note='Reviewed feature diff and API behavior', target=str(project),
                           commit=git(project, 'rev-parse', 'HEAD'), **kwargs)


def test_legacy_review_and_integration_unlock(project):
    assert not executable_tasks(read_tasks_document())
    review_task(args(project))
    assert not executable_tasks(read_tasks_document())
    integrate_task(args(project))
    doc = read_tasks_document()
    assert [task['id'] for task in executable_tasks(doc)] == ['002']
    assert projection(doc)[0]['integration'] == 'confirmed'
    # New execution invalidates even a previously confirmed integration.
    write_run_record(dict(task_num='001', run_id='new-run', status='starting', pid=0))
    assert not executable_tasks(read_tasks_document())
    assert projection(read_tasks_document())[0]['execution'] == 'interrupted'


def test_review_refuses_task_managed_by_foreman(project):
    doc = read_tasks_document()
    doc['tasks'][0].update(status='AWAITING_REVIEW', execution_id='001-20260101-000000-abcdef123456')
    write_tasks_document(doc)
    with pytest.raises(CliError, match='foreman'):
        review_task(args(project))
    task = read_tasks_document()['tasks'][0]
    assert task['status'] == 'AWAITING_REVIEW' and 'review' not in task


def test_edit_contract_invalidates_receipts(project):
    review_task(args(project))
    doc = read_tasks_document()
    doc['tasks'][0]['sections'][0]['body'] = 'Different scope'
    write_tasks_document(doc)
    with pytest.raises(CliError, match='审查'):
        integrate_task(args(project))
    assert projection(read_tasks_document())[0]['review'] == 'pending'


def test_integration_requires_review_clean_target_and_passing_acceptance(project):
    with pytest.raises(CliError, match='审查'):
        integrate_task(args(project))
    review_task(args(project))
    (project / 'artifact.txt').write_text('bad')
    with pytest.raises(CliError, match='干净'):
        integrate_task(args(project))
    git(project, 'add', '.')
    git(project, 'commit', '-qm', 'bad')
    with pytest.raises(CliError, match='未通过'):
        integrate_task(args(project))
    assert not executable_tasks(read_tasks_document())


def test_target_reset_invalidates_integration(project):
    review_task(args(project))
    git(project, 'commit', '--allow-empty', '-qm', 'delivery')
    integrate_task(args(project))
    assert integration_valid(read_tasks_document()['tasks'][0])
    git(project, 'checkout', '--detach', 'HEAD~1')
    assert not integration_valid(read_tasks_document()['tasks'][0])


def test_show_and_context_do_not_migrate_markdown(project):
    Path('planning/tasks.json').unlink()
    before = Path('planning/codex-tasks.md').read_bytes()
    doc = read_tasks_document(migrate=False)
    assert projection(doc)[0]['integration'] == 'unconfirmed'
    pack = context_pack('1')
    assert 'preserve API' in pack and 'acceptance_commands' in pack
    assert not Path('planning/tasks.json').exists()
    assert Path('planning/codex-tasks.md').read_bytes() == before


def test_isolated_worktree_is_not_target(project):
    task = read_tasks_document()['tasks'][0]
    record = dict(task_num='001', run_id='r1', backend='app-server', status='success', pid=0,
                  isolated=True, source_workdir=str(project), workdir='/other',
                  verification=dict(passed=True, task_fingerprint=task_fingerprint(task)))
    write_run_record(record)
    review_task(args(project))
    another = project.parent / 'another'
    git(project, 'worktree', 'add', '--detach', str(another))
    options = args(project)
    options.target = str(another)
    with pytest.raises(CliError, match='原始仓库'):
        integrate_task(options)


def test_context_budget(project):
    doc = read_tasks_document()
    doc['tasks'][0]['sections'][0]['body'] = 'x' * 65536
    write_tasks_document(doc)
    with pytest.raises(CliError, match='64 KiB'):
        context_pack('001')


def test_failed_reintegration_revokes_prior_confirmation(project):
    review_task(args(project))
    integrate_task(args(project))
    assert executable_tasks(read_tasks_document())
    (project / 'artifact.txt').write_text('bad')
    git(project, 'add', '.')
    git(project, 'commit', '-qm', 'regression')
    with pytest.raises(CliError, match='未通过'):
        integrate_task(args(project))
    assert executable_tasks(read_tasks_document()) == []
