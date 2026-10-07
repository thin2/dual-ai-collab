from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skill/scripts'))
import task_manager
import task_scheduler
from tasks_store import CliError, read_tasks_document, write_tasks_document, executable_tasks
from task_visualization import find_critical_path, detect_circular_dependencies, generate_analysis_report


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, str(ROOT / 'skill/scripts/cli.py'), *args],
                          cwd=tmp_path, capture_output=True, text=True, timeout=10)


def test_template_add_round_trip_and_reject_duplicates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = ('templates', 'create', 'feature', '001', '--var', 'feature_name=登录', '--add')
    assert cli(tmp_path, *args).returncode == 0
    board = read_tasks_document()
    assert board['tasks'][0]['id'] == '001'
    assert cli(tmp_path, 'select').stdout.startswith('2|001|')
    markdown = Path('planning/codex-tasks.md').read_text()
    assert '### 验收标准' in markdown and '登录' in markdown
    before = Path('planning/tasks.json').read_bytes()
    assert cli(tmp_path, *args).returncode == 1
    # Leading zero aliases also collide.
    assert cli(tmp_path, 'templates', 'create', 'docs', '1', '--var', 'topic=x', '--add').returncode == 1
    for dep in ('001', '999'):
        result = cli(tmp_path, 'templates', 'create', 'docs', '002', '--var', 'topic=x', '--add', '--depends-on', dep)
        if dep == '001':
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode == 1
    assert len(read_tasks_document()['tasks']) == 2
    assert before != Path('planning/tasks.json').read_bytes()
    assert cli(tmp_path, 'select', '--parallel').stdout.count('|') == 2
    assert cli(tmp_path, 'update', '001', 'DONE').returncode == 0
    assert cli(tmp_path, 'select', '--parallel').stdout.startswith('3|002|')
    assert 't001 --> t002' in cli(tmp_path, 'visualize').stdout
    assert '001 → 002' in cli(tmp_path, 'analyze').stdout


def test_template_invalid_input_does_not_write(tmp_path):
    base = ('templates', 'create', 'docs', '002', '--var', 'topic=x', '--add')
    for extra in [('--depends-on', '002'), ('--depends-on', '999'), ('--var', 'invalid')]:
        result = cli(tmp_path, *base, *extra)
        assert result.returncode == 1
        assert 'Traceback' not in result.stderr
        assert not (tmp_path / 'planning/tasks.json').exists()


def task(id, status='OPEN', deps='无', priority='P2', level='normal'):
    return dict(id=id, status=status, dependencies=deps, priority=priority, execution_level=level)


RESOURCES = dict(cpu_percent=10, memory_percent=20, available_memory_mb=10000, disk_usage_percent=20)


def test_smart_select_schedule_share_eligible_tasks(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_tasks_document({'tasks': [task('001', 'DONE'), task('002', deps='#001'),
                                  task('003', deps='#002', priority='P0'), task('004', level='quick')]})
    monkeypatch.setattr(task_scheduler, 'get_system_resources', lambda: RESOURCES)
    doc = read_tasks_document()
    ranking = task_scheduler.rank_available_tasks(doc['tasks'], doc)
    assert {t['id'] for t in ranking} == {'002', '004'}
    task_manager.cmd_select(False, 'planning/tasks.json', smart=True)
    assert f"|{ranking[0]['id']}|" in capsys.readouterr().out
    report = task_scheduler.generate_schedule_report()
    assert '任务 #003:' not in report and f"1. 任务 #{ranking[0]['id']}:" in report
    overloaded = dict(RESOURCES, memory_percent=95)
    assert [t['id'] for t in task_scheduler.rank_available_tasks(doc['tasks'], doc, system_resources=overloaded)] == ['004']


def test_empty_schedule_and_invalid_dependencies(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(task_scheduler, 'get_system_resources', lambda: RESOURCES)
    write_tasks_document({'tasks': []})
    assert '剩余任务: 0' in task_scheduler.generate_schedule_report()
    with pytest.raises(CliError):
        write_tasks_document({'tasks': [task('001', deps='unknown')]})
    write_tasks_document({'tasks': [task('001', deps='#999')]})
    assert executable_tasks(read_tasks_document()) == []
    with pytest.raises(CliError, match='不存在'):
        generate_analysis_report()


def test_cycles_do_not_recurse_forever(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_tasks_document({'tasks': [task('001', deps='#2'), task('002', deps='#001')]})
    doc = read_tasks_document()
    assert detect_circular_dependencies(doc)
    assert '循环依赖' in generate_analysis_report()
    with pytest.raises(CliError):
        find_critical_path(doc)
    assert executable_tasks(doc) == []


def test_legacy_template_schema_is_readable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_tasks_document({'tasks': [{'task_num': '001', 'status': 'DONE', 'dependencies': []},
                                  {'task_num': '002', 'status': 'OPEN', 'dependencies': ['001']}]})
    assert [t['id'] for t in executable_tasks(read_tasks_document())] == ['002']


def test_template_add_rejects_cycle_without_changing_board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_tasks_document({'tasks': [task('001', deps='#002')]})
    before = Path('planning/tasks.json').read_bytes()
    result = cli(tmp_path, 'templates', 'create', 'docs', '002', '--var', 'topic=x', '--depends-on', '001', '--add')
    assert result.returncode == 1 and '循环' in result.stderr
    assert Path('planning/tasks.json').read_bytes() == before


def test_split_templates_keep_numeric_ids_and_dependencies():
    from task_templates import create_task_from_template, auto_split_task
    original = create_task_from_template('feature', '010', feature_name='test')
    original['estimated_hours'] = 4.5
    split = auto_split_task(original, max_hours=2)
    assert [item['id'] for item in split] == ['010', '011', '012']
    assert [item['dependencies'] for item in split] == ['无', '#010', '#011']
    assert all(item['estimated_hours'] <= 2 for item in split)
