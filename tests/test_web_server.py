"""HTTP contracts and persistence integration for the Task Management monitor."""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_server
from web_server import create_app


@pytest.fixture(autouse=True)
def isolate_user_configuration(monkeypatch):
    monkeypatch.delenv('TASK_MANAGEMENT_PROJECTS_FILE', raising=False)
    # Never read real Factory settings or sessions from HTTP tests.
    monkeypatch.setattr(web_server, 'check_team', Mock(return_value=[]))
    monkeypatch.setattr(web_server, 'audit_runs', Mock(return_value=[]))


@pytest.fixture
def client(tmp_path):
    planning = tmp_path / 'planning'
    planning.mkdir()
    (planning / 'tasks.json').write_text(json.dumps({'tasks': [
        {'id': '001', 'title': '测试任务', 'status': 'OPEN', 'priority': 2,
         'estimated_hours': 0, 'dependencies': [], 'role': 'backend', 'files': ['app.py'],
         'failed_attempts': 3, 'integration': None,
         'sections': [{'heading': '验收', 'body': '`pytest`'}], 'description': '实现接口'},
        {'id': '002', 'title': 'Finished', 'status': 'DONE', 'dependencies': ['001']},
    ]}), encoding='utf-8')
    app = create_app(tmp_path)
    app.config['TESTING'] = True
    return app.test_client()


def write_config(client, data):
    path = Path(client.application.config['TASK_FILE']).parents[1] / '.task-management/config.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_read_and_update(client):
    response = client.get('/api/tasks')
    assert response.status_code == 200
    assert response.json['success'] is True
    assert len(response.json['tasks']) == 2
    original = response.json['tasks'][0]
    assert original['estimated_hours'] == 0
    assert original['dependencies'] == []
    assert original['model'] is None and original['droid'] is None
    assert original['board'] == {'integration': 'pending', 'waiting': []}
    assert client.get('/api/tasks/1').json['task'] == original
    assert client.put('/api/tasks/001', json={'status': 'IN_PROGRESS'}).status_code == 200
    task = client.get('/api/tasks/001').json['task']
    assert task['status'] == 'IN_PROGRESS'
    assert task['failed_attempts'] == 3
    assert task['sections'] == original['sections']
    assert task['description'] == original['description']
    task_file = Path(client.application.config['TASK_FILE'])
    assert json.loads(task_file.read_text())['tasks'][0]['status'] == 'IN_PROGRESS'
    assert 'IN_PROGRESS' in task_file.with_suffix('.md').read_text()


@pytest.mark.parametrize('status', sorted(web_server.EDITABLE_STATUSES))
def test_editable_statuses_and_retry_reset(client, status):
    assert client.put('/api/tasks/001', json={'status': status, 'reset_retries': True}).status_code == 200
    task = client.get('/api/tasks/001').json['task']
    assert task['status'] == status
    assert task['failed_attempts'] == 0


@pytest.mark.parametrize('payload', [
    {}, {'status': 'bogus'}, {'status': []}, [], None,
    {'status': 'PENDING', 'reset_retries': 1}, {'status': 'PENDING', 'reset_retries': None},
    {'status': 'PENDING', 'reset_retries': 'true'},
])
def test_invalid_body(client, payload):
    response = client.put('/api/tasks/001', data=json.dumps(payload), content_type='application/json')
    assert response.status_code == 400
    assert response.json['success'] is False
    assert client.get('/api/tasks/001').json['task']['status'] == 'OPEN'


@pytest.mark.parametrize('status', ['DONE', 'VERIFIED'])
def test_completion_requires_skill_integration(client, status):
    response = client.put('/api/tasks/001', json={'status': status})
    assert response.status_code == 400
    assert 'integrate' in response.json['error']
    assert client.get('/api/tasks/001').json['task']['status'] == 'OPEN'


@pytest.mark.parametrize('method,url,kwargs,code', [
    ('get', '/api/tasks/999', {}, 404),
    ('put', '/api/tasks/999', {'json': {'status': 'PENDING'}}, 404),
    ('get', '/api/unknown', {}, 404),
    ('post', '/api/tasks', {}, 405),
    ('put', '/api/tasks/001', {'data': '{', 'content_type': 'application/json'}, 400),
    ('put', '/api/tasks/001', {'data': 'text', 'content_type': 'text/plain'}, 415),
])
def test_http_errors(client, method, url, kwargs, code):
    response = getattr(client, method)(url, **kwargs)
    assert response.status_code == code
    assert response.json['success'] is False


def test_board_completion_and_dependencies(client):
    path = Path(client.application.config['TASK_FILE'])
    doc = json.loads(path.read_text())
    doc['tasks'].extend([
        {'id': '003', 'status': 'DONE', 'integration': {'commit': 'abc'}},
        {'id': '004', 'status': 'PENDING', 'dependencies': '#002, #3, #missing'},
        {'id': '005', 'status': 'VERIFIED', 'integration': {'commit': 'def'}},
    ])
    path.write_text(json.dumps(doc))
    result = client.get('/api/board').json
    assert result['stats']['total'] == 5
    assert result['stats']['by_status']['OPEN'] == 1
    assert result['stats']['by_status']['BLOCKED'] == 0
    assert result['stats']['completed'] == 1
    assert result['stats']['completion_rate'] == 20.0
    assert result['rows'][1]['integration'] == 'pending'
    assert result['rows'][3]['waiting'] == ['002', 'missing']
    assert client.get('/api/tasks/004').json['task']['board']['waiting'] == ['002', 'missing']


def test_empty_board(client):
    Path(client.application.config['TASK_FILE']).write_text('{"tasks": []}')
    assert client.get('/api/board').json['stats']['completion_rate'] == 0


def test_history_is_new_only_sorted_and_sanitized(client, caplog):
    assert client.get('/api/history').json['history'] == []
    root = Path(client.application.config['TASK_FILE']).parents[1]
    old = root / '.dual-ai-collab/history'
    old.mkdir(parents=True)
    (old / 'ignored.json').write_text('{')
    directory = Path(client.application.config['HISTORY_DIR'])
    directory.mkdir(parents=True)
    for name, date in [('001', '2026-10-07'), ('002', '2026-10-08')]:
        (directory / f'{name}.json').write_text(json.dumps({
            'task_id': name, 'start_time': date, 'status': 'failed',
            'error_message': 'private-exception-detail', 'arbitrary_private_field': 'hidden',
        }))
    (directory / 'ignored.txt').write_text('{')
    response = client.get('/api/history')
    assert response.status_code == 200
    assert [record['task_id'] for record in response.json['history']] == ['002', '001']
    assert 'private' not in response.get_data(as_text=True)
    (directory / 'broken.json').write_text('private-exception-detail')
    response = client.get('/api/history')
    assert response.status_code == 500
    assert response.json == {'success': False, 'error': 'Internal server error'}
    assert 'private-exception-detail' not in caplog.text


@pytest.mark.parametrize('contents', ['{', '[]', '{"tasks": {}}', '{"tasks": [null]}'])
def test_storage_failure(client, contents):
    Path(client.application.config['TASK_FILE']).write_text(contents)
    response = client.get('/api/tasks')
    assert response.status_code == 500
    assert response.json == {'success': False, 'error': 'Internal server error'}


def test_team_and_task_models_are_whitelisted(client):
    write_config(client, {'roles': {'backend': {
        'droid': 'tm-backend', 'model': 'custom:test', 'description': '后端', 'read_only': False,
        'private_extra': 'hidden',
    }}, 'parallel': {'max_parallel': 3, 'max_retries': 4, 'private_extra': 'hidden'},
        'private_extra': 'hidden'})
    response = client.get('/api/team')
    assert response.json == {'success': True, 'roles': {'backend': {
        'droid': 'tm-backend', 'model': 'custom:test', 'description': '后端', 'read_only': False,
    }}, 'parallel': {'max_parallel': 3, 'max_retries': 4}}
    task = client.get('/api/tasks/001').json['task']
    assert task['model'] == 'custom:test' and task['droid'] == 'tm-backend'
    assert client.get('/api/tasks/002').json['task']['model'] is None
    web_server.check_team.assert_not_called()
    web_server.audit_runs.assert_not_called()


def test_team_check_and_audit_are_explicit_and_project_scoped(client):
    root = Path(client.application.config['TASK_FILE']).parents[1]
    checks = [dict(role='backend', droid='tm-backend', model='custom:test', ok=False,
                   problems=['TCP 连接不可用'], private_extra='hidden')]
    web_server.check_team.return_value = checks
    response = client.get('/api/team/check')
    assert response.json == {'success': True, 'checks': [
        {key: value for key, value in checks[0].items() if key != 'private_extra'}]}
    web_server.check_team.assert_called_once_with(root)
    assert client.get('/api/team/audit').json == {'success': True, 'records': []}
    web_server.audit_runs.assert_called_once_with(root)
    records = [dict(session_id='s1', title='tm-backend: example', role='backend',
                    expected='custom:test', actual='custom:other', ok=False, private_extra='hidden')]
    web_server.audit_runs.return_value = records
    assert client.get('/api/team/audit').json['records'] == [
        {key: value for key, value in records[0].items() if key != 'private_extra'}]


@pytest.mark.parametrize('endpoint,function', [('check', 'check_team'), ('audit', 'audit_runs')])
def test_team_errors_are_not_success_or_exception_leaks(client, endpoint, function, caplog):
    getattr(web_server, function).side_effect = RuntimeError('private-exception-detail')
    response = client.get('/api/team/' + endpoint)
    assert response.status_code == 500
    assert response.json == {'success': False, 'error': 'Internal server error'}
    assert 'private-exception-detail' not in caplog.text


@pytest.mark.parametrize('contents', ['{', '[]', '{"roles": []}', '{"roles": {"backend": null}}'])
def test_bad_configuration_is_visible(client, contents):
    path = write_config(client, {})
    path.write_text(contents)
    for resource in ['tasks', 'team', 'team/check', 'team/audit', 'batch']:
        response = client.get('/api/' + resource)
        assert response.status_code == 500
        assert response.json['success'] is False
    web_server.check_team.assert_not_called()
    web_server.audit_runs.assert_not_called()


def test_batch_uses_library_selection_without_dispatch_or_context(client):
    write_config(client, {'roles': {'backend': {'droid': 'tm-backend', 'model': 'custom:test'}}})
    tasks = [
        {'id': '001', 'title': 'First', 'status': 'PENDING', 'files': ['src/a.py'], 'role': 'backend'},
        {'id': '002', 'title': 'Conflict', 'status': 'TODO', 'files': ['src/a.py']},
        {'id': '003', 'title': 'Dependency', 'status': 'OPEN', 'files': ['src/c.py'], 'dependencies': '#007'},
        {'id': '004', 'title': 'Second', 'status': 'PENDING', 'files': ['src/b.py']},
        {'id': '005', 'title': 'Limit', 'status': 'PENDING', 'files': ['src/d.py']},
        {'id': '006', 'title': 'Missing role', 'status': 'PENDING', 'role': 'missing'},
        {'id': '007', 'title': 'Unconfirmed', 'status': 'DONE'},
    ]
    Path(client.application.config['TASK_FILE']).write_text(json.dumps({'tasks': tasks}))
    result = client.get('/api/batch')
    assert result.status_code == 200
    assert [entry['task_id'] for entry in result.json['batch']] == ['001', '004']
    first = result.json['batch'][0]
    assert set(first) == {'task_id', 'task_title', 'role', 'droid', 'model', 'complexity', 'files'}
    assert first['model'] == 'custom:test' and first['droid'] == 'tm-backend'
    skipped = {entry['id']: entry['reason'] for entry in result.json['skipped']}
    assert '重叠' in skipped['002']
    assert '依赖未完成' in skipped['003']
    assert '并发上限' in skipped['005']
    assert '未配置' in skipped['006']
    assert json.loads(Path(client.application.config['TASK_FILE']).read_text())['tasks'] == tasks
    web_server.check_team.assert_not_called()


def test_batch_reuses_executor_projection(client, monkeypatch):
    planner = Mock(return_value={'batch': [{
        'task_id': '001', 'task_title': 'Preview', 'role': None, 'droid': 'worker',
        'model': None, 'complexity': 'light', 'files': [], 'prompt': 'private',
        'context': 'private', 'task_args': {'prompt': 'private'},
    }], 'skipped': [{'id': '002', 'reason': 'waiting', 'private_extra': 'hidden'}]})
    monkeypatch.setattr(web_server.TaskExecutor, 'plan_batch', planner)
    result = client.get('/api/batch')
    planner.assert_called_once_with()
    assert 'private' not in result.get_data(as_text=True)


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://foreign.example'},
    {'Origin': 'https://localhost'},
    {'Origin': 'null'},
    {'Sec-Fetch-Site': 'cross-site'},
])
def test_cross_site_writes_rejected(client, headers):
    assert client.put('/api/tasks/001', json={'status': 'PENDING'}, headers=headers).status_code == 403


def test_same_origin_and_request_size(client):
    assert client.put('/api/tasks/001', json={'status': 'PENDING'},
                      headers={'Origin': 'http://localhost'}).status_code == 200
    result = client.put('/api/tasks/001', json={'status': 'PENDING', 'padding': 'x' * 65536})
    assert result.status_code == 413
    assert result.json['success'] is False


@pytest.mark.parametrize('url,method', [
    ('/api/runs/001', 'get'), ('/api/runs/001/start', 'post'),
    ('/api/projects/default/runs/001/stop', 'post'),
])
def test_legacy_execution_endpoints_removed(client, url, method):
    assert getattr(client, method)(url).status_code == 404


def test_team_routes_pass_template_context_without_requiring_template(client, monkeypatch):
    render = Mock(return_value='team placeholder')
    monkeypatch.setattr(web_server, 'render_template', render)
    for url in ['/team', '/project/default/team']:
        assert client.get(url).status_code == 200
        args, context = render.call_args
        assert args == ('team.html',)
        assert context['project']['id'] == 'default'
        assert set(context['project']) == {'id', 'name', 'path', 'available'}
        assert context['projects'] == [context['project']]
