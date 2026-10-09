#!/usr/bin/env python3
"""Local multi-project task journal. Run python web_server.py [port]."""
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / 'skill/scripts'))
import task_manager
import task_board
import tasks_store
from project_context import ProjectRegistry, ProjectError

VALID_STATUSES = frozenset({
    'TODO', 'OPEN', 'IN_PROGRESS', 'AWAITING_REVIEW', 'AWAITING_INTEGRATION',
    'DONE', 'VERIFIED', 'REJECTED', 'FAILED',
})


def create_app(repo_root=None, registry_file=None):
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    registry = ProjectRegistry(root, registry_file)
    app = Flask(__name__)
    app.config.update(TASK_FILE=str(root / 'planning/tasks.json'),
                      HISTORY_DIR=str(root / '.dual-ai-collab/history'),
                      PROJECT_REGISTRY=str(registry.file), MAX_CONTENT_LENGTH=65536)
    app.extensions['projects'] = registry

    @app.before_request
    def check_origin():
        # Local registration and task edits must originate from this app, not another site.
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            origin = request.headers.get('Origin')
            if origin and urlsplit(origin).netloc != request.host:
                abort(403, description='跨站修改请求已拒绝')

    def document(project):
        task_file = project.task_file
        if not task_file.exists() and not task_file.with_name('codex-tasks.md').exists():
            return {'tasks': []}
        return tasks_store.read_tasks_document(task_file, migrate=False)

    def board_data(project):
        project.runtime_dir
        doc = document(project)
        rows = task_board.projection(doc, str(project.task_file), project_root=project.root)
        return doc, rows

    def lookup(project, task_id):
        task = tasks_store.find_task(document(project), task_id)
        if task is None:
            abort(404, description='Task not found')
        return task

    def page_context(project):
        project.task_file
        return dict(project=project.as_dict(), projects=[p.as_dict() for p in registry.list()])

    @app.errorhandler(ProjectError)
    def project_error(error):
        return jsonify(success=False, error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = app.json.dumps({'success': False, 'error': error.description})
        response.content_type = 'application/json'
        return response

    @app.errorhandler(Exception)
    def server_error(error):
        app.logger.exception('Request failed')
        return jsonify(success=False, error='Internal server error'), 500

    @app.get('/api/projects')
    def get_projects():
        return jsonify(success=True, projects=[p.as_dict() for p in registry.list()])

    @app.post('/api/projects')
    def add_project():
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400, description='Expected a JSON object')
        project = registry.add(data.get('name'), data.get('path'))
        return jsonify(success=True, project=project.as_dict()), 201

    @app.get('/api/tasks')
    @app.get('/api/projects/<project_id>/tasks')
    def get_tasks(project_id='default'):
        project = registry.get(project_id)
        doc, rows = board_data(project)
        indexed = {row['id']: row for row in rows}
        return jsonify(success=True, project=project.as_dict(), tasks=[
            dict(task, board=indexed[task['id']]) for task in doc['tasks']])

    @app.get('/api/tasks/<task_id>')
    @app.get('/api/projects/<project_id>/tasks/<task_id>')
    def get_task(task_id, project_id='default'):
        project = registry.get(project_id)
        task = lookup(project, task_id)
        _, rows = board_data(project)
        row = next(item for item in rows if item['id'] == task['id'])
        return jsonify(success=True, project=project.as_dict(), task=dict(task, board=row))

    @app.put('/api/tasks/<task_id>')
    @app.put('/api/projects/<project_id>/tasks/<task_id>')
    def update_task(task_id, project_id='default'):
        project = registry.get(project_id)
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400, description='Expected a JSON object')
        status = data.get('status')
        if not isinstance(status, str) or status not in VALID_STATUSES:
            abort(400, description='Invalid or missing status field')
        task = lookup(project, task_id)
        if not task.get('status_explicit'):
            abort(409, description='Task has no explicit status')
        try:
            task_manager.cmd_update(task_id, status, str(project.task_file))
        except tasks_store.CliError:
            lookup(project, task_id)
            abort(409, description='Task could not be updated')
        return jsonify(success=True, message=f'任务 {task_id} 状态已更新为 {status}')

    @app.get('/api/board')
    @app.get('/api/projects/<project_id>/board')
    def get_board(project_id='default'):
        doc, rows = board_data(registry.get(project_id))
        counts = Counter(task.get('status', 'UNKNOWN') for task in doc['tasks'])
        completed = sum(row['integration'] == 'confirmed' for row in rows)
        return jsonify(success=True, rows=rows, stats={
            'total': len(rows),
            'by_status': {status: counts[status] for status in sorted(VALID_STATUSES | counts.keys())},
            'completed': completed,
            'completion_rate': round(completed / len(rows) * 100, 1) if rows else 0.0,
        })

    @app.get('/api/history')
    @app.get('/api/projects/<project_id>/history')
    def get_history(project_id='default'):
        project = registry.get(project_id)
        records = []
        for path in sorted(project.path('.dual-ai-collab/history').glob('*.json')):
            record = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(record, dict):
                raise ValueError('Invalid history record')
            records.append(record)
        records.sort(key=lambda record: record.get('start_time') or '', reverse=True)
        return jsonify(success=True, history=records)

    @app.get('/')
    @app.get('/project/<project_id>/tasks')
    def index(project_id='default'):
        return render_template('index.html', **page_context(registry.get(project_id)))

    @app.get('/task/<task_id>')
    @app.get('/project/<project_id>/task/<task_id>')
    def task_detail(task_id, project_id='default'):
        project = registry.get(project_id)
        lookup(project, task_id)
        return render_template('task_detail.html', task_id=task_id, **page_context(project))

    return app


app = create_app(registry_file=os.environ.get('DUAL_AI_PROJECTS_FILE'))

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    print(f'任务工作簿：http://localhost:{port}')
    app.run(host='127.0.0.1', port=port, debug=False)
