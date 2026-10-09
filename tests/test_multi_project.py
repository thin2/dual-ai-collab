"""Multiple projects, identical task IDs and concurrent requests stay isolated."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_server import create_app
from project_context import ProjectRegistry, ProjectError
from tasks_store import write_tasks_document
from task_board import projection


def seed(root, title, execution):
    root.mkdir()
    write_tasks_document({'tasks': [dict(id='001', title=title, status='OPEN')]}, root / 'planning/tasks.json')
    runs = root / '.dual-ai-collab/runs'
    runs.mkdir(parents=True)
    (runs / 'task-001.json').write_text(json.dumps(dict(task_num='001', run_id=title, status=execution, pid=0)))
    history = root / '.dual-ai-collab/history'
    history.mkdir()
    (history / '001.json').write_text(json.dumps(dict(task_num='001', title=title, start_time='2026-10-09')))


@pytest.fixture
def projects(tmp_path, monkeypatch):
    a, b, unrelated = [tmp_path / name for name in ('alpha', 'beta', 'unrelated')]
    seed(a, 'Alpha only', 'success')
    seed(b, 'Beta only', 'blocked')
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    app = create_app(a)
    app.config['TESTING'] = True
    with app.test_client() as client:
        result = client.post('/api/projects', json={'name': 'Beta', 'path': str(b)})
        assert result.status_code == 201
        beta = result.json['project']['id']
    return app, a, b, beta, unrelated


def test_paths_tasks_runs_history_and_updates_are_project_scoped(projects):
    app, a, b, beta, unrelated = projects
    client = app.test_client()
    for project_id, title, execution in [('default', 'Alpha only', 'success'), (beta, 'Beta only', 'blocked')]:
        prefix = '/api/projects/' + project_id
        response = client.get(prefix + '/tasks/1')
        assert response.status_code == 200
        assert response.json['task']['title'] == title
        assert response.json['task']['board']['execution'] == execution
        assert client.get(prefix + '/history').json['history'][0]['title'] == title
    assert client.put(f'/api/projects/{beta}/tasks/001', json={'status': 'IN_PROGRESS'}).status_code == 200
    assert client.get('/api/tasks/001').json['task']['status'] == 'OPEN'
    assert client.get(f'/api/projects/{beta}/tasks/001').json['task']['status'] == 'IN_PROGRESS'
    assert Path.cwd() == unrelated
    assert list(unrelated.iterdir()) == []
    # Registry survives a server restart.
    other = create_app(a).test_client()
    assert other.get(f'/api/projects/{beta}/tasks').json['tasks'][0]['title'] == 'Beta only'


def test_concurrent_project_requests(projects):
    app, a, b, beta, unrelated = projects
    def update(project_id, status):
        with app.test_client() as client:
            result = client.put(f'/api/projects/{project_id}/tasks/001', json={'status': status})
            return result.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: update(*args), [('default', 'IN_PROGRESS'), (beta, 'AWAITING_REVIEW')]))
    assert results == [200, 200]
    assert json.loads((a / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'IN_PROGRESS'
    assert json.loads((b / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'AWAITING_REVIEW'
    assert Path.cwd() == unrelated


def test_registration_validation_and_unknown_project(projects, tmp_path):
    app, a, b, beta, _ = projects
    client = app.test_client()
    for payload in ({}, [], {'name': 'Bad', 'path': 'relative'}, {'name': 'Bad', 'path': str(tmp_path / 'missing')}):
        assert client.post('/api/projects', json=payload).status_code == 400
    assert client.post('/api/projects', json={'name': 'Again', 'path': str(b / '..' / 'beta')}).status_code == 409
    alias = tmp_path / 'alias'
    alias.symlink_to(b, target_is_directory=True)
    assert client.post('/api/projects', json={'name': 'Alias', 'path': str(alias)}).status_code == 409
    assert client.get('/api/projects/unknown/tasks').status_code == 404
    assert client.put('/api/projects/unknown/tasks/001', json={'status': 'DONE'}).status_code == 404
    assert client.post('/api/projects', json={'name': 'Bad', 'path': str(tmp_path)}, headers={'Origin': 'https://foreign.example'}).status_code == 403


def test_empty_project_and_unavailable_path(projects, tmp_path):
    app, _, _, _, _ = projects
    root = tmp_path / 'empty'
    root.mkdir()
    client = app.test_client()
    project_id = client.post('/api/projects', json={'name': 'Empty', 'path': str(root)}).json['project']['id']
    assert client.get(f'/api/projects/{project_id}/tasks').json['tasks'] == []
    assert client.get(f'/api/projects/{project_id}/board').json['stats']['total'] == 0
    assert list(root.iterdir()) == []  # Listing does not initialize a task board.
    root.rmdir()
    assert client.get(f'/api/projects/{project_id}/tasks').status_code == 409
    assert client.get('/api/projects').json['projects'][-1]['available'] is False


def test_project_pages_keep_project_links_and_no_grill(projects):
    app, _, _, beta, _ = projects
    client = app.test_client()
    page = client.get(f'/project/{beta}/task/001')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert f'/project/{beta}/tasks' in html
    assert f'const projectId = "{beta}"' in html
    assert '登记项目' in html and 'grill' not in html
    assert client.get(f'/project/{beta}/tasks').status_code == 200


def test_registry_concurrent_add_and_corruption(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    dirs = [tmp_path / 'one', tmp_path / 'two']
    for path in dirs:
        path.mkdir()
    registry = ProjectRegistry(root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda path: registry.add(path.name, str(path)), dirs))
    assert len(registry.list()) == 3
    registry.file.write_text('{')
    with pytest.raises(ProjectError, match='注册表'):
        registry.add('third', str(tmp_path))
    assert registry.file.read_text() == '{'


def test_external_planning_symlink_rejected(projects, tmp_path):
    app, a, _, _, _ = projects
    root = tmp_path / 'linked'
    root.mkdir()
    (root / 'planning').symlink_to(a / 'planning', target_is_directory=True)
    response = app.test_client().post('/api/projects', json={'name': 'Linked', 'path': str(root)})
    assert response.status_code == 409
    assert '仓库之外' in response.json['error']
