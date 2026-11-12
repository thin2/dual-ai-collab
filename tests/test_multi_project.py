"""Multiple projects, concurrent requests and symlink boundaries stay isolated."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'foreman'))
from lib.store import write_tasks_document

import web_server
from web_projects import ProjectError, ProjectRegistry
from web_server import create_app


@pytest.fixture(autouse=True)
def isolate_user_configuration(monkeypatch):
    monkeypatch.delenv('TASK_MANAGEMENT_PROJECTS_FILE', raising=False)
    monkeypatch.setattr(web_server, 'check_team', Mock(return_value=[]))
    monkeypatch.setattr(web_server, 'audit_runs', Mock(return_value=[]))


def seed(root, title, model):
    root.mkdir()
    write_tasks_document({'tasks': [
        dict(id='001', title=title, status='OPEN', role='backend', files=['app.py']),
    ]}, root / 'planning/tasks.md')
    history = root / '.task-management/history'
    history.mkdir(parents=True)
    (history / '001.json').write_text(json.dumps(dict(task_id='001', title=title, start_time='2026-10-09')))
    (history.parent / 'config.json').write_text(json.dumps({
        'roles': {'backend': {'droid': 'tm-backend', 'model': model, 'description': title}},
    }))


@pytest.fixture
def projects(tmp_path, monkeypatch):
    a, b, unrelated = [tmp_path / name for name in ('alpha', 'beta', 'unrelated')]
    seed(a, 'Alpha only', 'custom:alpha')
    seed(b, 'Beta only', 'custom:beta')
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    app = create_app(a)
    app.config['TESTING'] = True
    with app.test_client() as client:
        result = client.post('/api/projects', json={'name': 'Beta', 'path': str(b)})
        assert result.status_code == 201
        beta = result.json['project']['id']
    return app, a, b, beta, unrelated


def test_tasks_config_history_and_updates_are_project_scoped(projects):
    app, a, b, beta, unrelated = projects
    client = app.test_client()
    for project_id, title, model, root in [
        ('default', 'Alpha only', 'custom:alpha', a), (beta, 'Beta only', 'custom:beta', b),
    ]:
        prefix = '/api/projects/' + project_id
        response = client.get(prefix + '/tasks/1')
        assert response.status_code == 200
        assert response.json['task']['title'] == title
        assert response.json['task']['model'] == model
        assert client.get(prefix + '/history').json['history'][0]['title'] == title
        assert client.get(prefix + '/team').json['roles']['backend']['model'] == model
        assert client.get(prefix + '/batch').json['batch'][0]['model'] == model
        assert client.get(prefix + '/team/check').status_code == 200
        web_server.check_team.assert_called_with(root)
        assert client.get(prefix + '/team/audit').status_code == 200
        web_server.audit_runs.assert_called_with(root)
    assert client.put(f'/api/projects/{beta}/tasks/001', json={'status': 'IN_PROGRESS'}).status_code == 200
    assert client.get('/api/tasks/001').json['task']['status'] == 'OPEN'
    assert client.get(f'/api/projects/{beta}/tasks/001').json['task']['status'] == 'IN_PROGRESS'
    assert Path.cwd() == unrelated
    assert list(unrelated.iterdir()) == []
    assert create_app(a).test_client().get(f'/api/projects/{beta}/tasks').json['tasks'][0]['title'] == 'Beta only'


def test_concurrent_project_requests(projects):
    app, a, b, beta, unrelated = projects

    def update(args):
        project_id, status = args
        with app.test_client() as client:
            assert client.get(f'/api/projects/{project_id}/team').status_code == 200
            return client.put(f'/api/projects/{project_id}/tasks/001', json={'status': status}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, [('default', 'IN_PROGRESS'), (beta, 'AWAITING_REVIEW')]))
    assert results == [200, 200]
    assert json.loads((a / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'IN_PROGRESS'
    assert json.loads((b / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'AWAITING_REVIEW'
    assert Path.cwd() == unrelated


def test_concurrent_updates_do_not_lose_tasks(projects):
    app, a, _, _, _ = projects
    path = a / 'planning/tasks.json'
    doc = json.loads(path.read_text())
    doc['tasks'].append(dict(id='002', title='Second', status='PENDING'))
    path.write_text(json.dumps(doc))

    def update(task_id):
        with app.test_client() as client:
            return client.put('/api/tasks/' + task_id, json={'status': 'IN_PROGRESS'}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(update, ['001', '002'])) == [200, 200]
    assert [task['status'] for task in json.loads(path.read_text())['tasks']] == ['IN_PROGRESS', 'IN_PROGRESS']


def test_registration_validation_and_unknown_project(projects, tmp_path):
    app, _, b, _, _ = projects
    client = app.test_client()
    for payload in ({}, [], {'name': 'Bad', 'path': 'relative'}, {'name': 'Bad', 'path': str(tmp_path / 'missing')}):
        assert client.post('/api/projects', json=payload).status_code == 400
    assert client.post('/api/projects', json={'name': 'Again', 'path': str(b / '..' / 'beta')}).status_code == 409
    alias = tmp_path / 'alias'
    alias.symlink_to(b, target_is_directory=True)
    assert client.post('/api/projects', json={'name': 'Alias', 'path': str(alias)}).status_code == 409
    assert client.get('/api/projects/unknown/tasks').status_code == 404
    assert client.put('/api/projects/unknown/tasks/001', json={'status': 'DONE'}).status_code == 404
    assert client.post('/api/projects', json={'name': 'Bad', 'path': str(tmp_path)},
                       headers={'Origin': 'https://foreign.example'}).status_code == 403


def test_empty_project_and_unavailable_path(projects, tmp_path):
    app, _, _, _, _ = projects
    root = tmp_path / 'empty'
    root.mkdir()
    client = app.test_client()
    project_id = client.post('/api/projects', json={'name': 'Empty', 'path': str(root)}).json['project']['id']
    prefix = f'/api/projects/{project_id}/'
    for resource, key in [('tasks', 'tasks'), ('board', 'rows'), ('history', 'history'),
                          ('team', 'roles'), ('batch', 'batch'), ('team/check', 'checks'), ('team/audit', 'records')]:
        response = client.get(prefix + resource)
        assert response.status_code == 200
        assert not response.json[key]
    assert list(root.iterdir()) == []
    root.rmdir()
    assert client.get(prefix + 'tasks').status_code == 409
    assert client.get('/api/projects').json['projects'][-1]['available'] is False


def test_project_pages_keep_project_context(projects, monkeypatch):
    app, _, _, beta, _ = projects
    client = app.test_client()
    page = client.get(f'/project/{beta}/task/001')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert f'/project/{beta}/tasks' in html
    assert f'const projectId = "{beta}"' in html
    assert '登记项目' in html and 'grill' not in html
    assert client.get(f'/project/{beta}/tasks').status_code == 200
    render = Mock(return_value='team placeholder')
    monkeypatch.setattr(web_server, 'render_template', render)
    assert client.get(f'/project/{beta}/team').status_code == 200
    assert render.call_args.args == ('team.html',)
    assert render.call_args.kwargs['project']['id'] == beta
    assert len(render.call_args.kwargs['projects']) == 2


def test_registry_concurrent_add_and_corruption(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    dirs = [tmp_path / 'one', tmp_path / 'two']
    for path in dirs:
        path.mkdir()
    registry = ProjectRegistry(root)
    assert registry.file == root / '.task-management/projects.json'
    # Independent instances exercise the file lock as well as in-process locking.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda path: ProjectRegistry(root).add(path.name, str(path)), dirs))
    assert len(registry.list()) == 3
    registry.file.write_text('{')
    with pytest.raises(ProjectError, match='注册表'):
        registry.add('third', str(tmp_path))
    assert registry.file.read_text() == '{'


def test_registry_environment_and_legacy_registry_ignored(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    root.mkdir()
    old = root / '.dual-ai-collab'
    old.mkdir()
    (old / 'projects.json').write_text('{')
    assert len(ProjectRegistry(root).list()) == 1
    selected = tmp_path / 'registry/projects.json'
    monkeypatch.setenv('TASK_MANAGEMENT_PROJECTS_FILE', str(selected))
    app = create_app(root)
    assert app.config['PROJECT_REGISTRY'] == str(selected)
    assert app.test_client().get('/api/projects').status_code == 200
    assert not selected.exists()
    other = tmp_path / 'other'
    other.mkdir()
    ProjectRegistry(root).add('Other', str(other))
    assert selected.exists()
    assert not (root / '.task-management').exists()
    assert (old / 'projects.json').read_text() == '{'


@pytest.mark.parametrize('relative', [
    'planning', 'planning/tasks.json', 'planning/tasks.md', 'planning/codex-tasks.json',
    'planning/tasks.json.tmp', 'planning/tasks.md.tmp', 'planning/tasks.json.lock',
    '.task-management', '.task-management/config.json', '.task-management/history',
    '.task-management/history/record.json', '.factory', '.factory/droids', '.factory/droids/tm-backend.md',
])
def test_external_data_symlinks_rejected_on_registration(projects, tmp_path, relative):
    app, _, _, _, _ = projects
    root, outside = tmp_path / 'linked', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(outside, target_is_directory=True)
    response = app.test_client().post('/api/projects', json={'name': 'Linked', 'path': str(root)})
    assert response.status_code == 409
    assert '仓库之外' in response.json['error']
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('relative', [
    'planning/tasks.json', 'planning/tasks.md', 'planning/codex-tasks.json',
    'planning/tasks.json.tmp', 'planning/tasks.md.tmp', 'planning/tasks.json.lock',
    '.task-management/config.json', '.task-management/history/record.json',
    '.factory/droids/tm-backend.md',
])
def test_symlinks_added_after_registration_are_rejected(projects, tmp_path, relative):
    app, _, b, beta, _ = projects
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = outside / 'data.json'
    target.write_text('do not read or modify')
    path = b / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    path.symlink_to(target)
    client = app.test_client()
    for resource in ['tasks', 'board', 'history', 'team', 'team/check', 'team/audit', 'batch']:
        assert client.get(f'/api/projects/{beta}/{resource}').status_code == 409
    assert client.put(f'/api/projects/{beta}/tasks/001', json={'status': 'PENDING'}).status_code == 409
    assert client.get('/api/tasks').status_code == 200
    assert target.read_text() == 'do not read or modify'
    web_server.check_team.assert_not_called()
    web_server.audit_runs.assert_not_called()


def test_derived_store_paths_and_role_traversal_are_checked(projects, tmp_path):
    app, _, b, beta, _ = projects
    md = b / 'planning/tasks.md'
    md.unlink()
    (b / 'other.md').write_text('placeholder')
    md.symlink_to(b / 'other.md')
    (b / 'other.json').symlink_to(tmp_path / 'outside.json')
    assert app.test_client().get(f'/api/projects/{beta}/tasks').status_code == 409
    md.unlink()
    config = b / '.task-management/config.json'
    config.write_text(json.dumps({'roles': {'../../outside': {'droid': 'bad', 'model': 'test'}}}))
    assert app.test_client().get(f'/api/projects/{beta}/team/check').status_code == 409
    web_server.check_team.assert_not_called()


def test_replaced_registered_root_is_unavailable(projects, tmp_path):
    app, _, b, beta, _ = projects
    moved = tmp_path / 'moved'
    b.rename(moved)
    b.symlink_to(moved, target_is_directory=True)
    client = app.test_client()
    assert client.get(f'/api/projects/{beta}/tasks').status_code == 409
    assert client.get('/api/projects').json['projects'][-1]['available'] is False


def test_legacy_task_filename_uses_library_fallback_without_get_migration(tmp_path):
    root = tmp_path / 'legacy'
    planning = root / 'planning'
    planning.mkdir(parents=True)
    legacy = planning / 'codex-tasks.json'
    legacy.write_text(json.dumps({'tasks': [dict(id='001', title='Compatible', status='TODO')]}))
    client = create_app(root).test_client()
    assert client.get('/api/tasks').json['tasks'][0]['title'] == 'Compatible'
    assert sorted(p.name for p in planning.iterdir()) == ['codex-tasks.json']
    assert client.put('/api/tasks/001', json={'status': 'PENDING'}).status_code == 200
    assert (planning / 'tasks.json').exists() and (planning / 'tasks.md').exists()
    assert json.loads(legacy.read_text())['tasks'][0]['status'] == 'TODO'
