#!/usr/bin/env python3
"""Local Task Management monitor. Run python web_server.py [port] [--project <root>]."""
import argparse
import json
import logging
import re
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

# The foreman library and the project registry lock files with fcntl, which Windows does not have.
if sys.platform == 'win32':
    sys.exit('Web UI 只支持 macOS 和 Linux；Windows 上请在 WSL 里运行。\n'
             'The web UI runs on macOS and Linux only. On Windows, run it inside WSL.')

REPO_ROOT = Path(__file__).resolve().parent
# In the source repository the library sits in foreman/; an installed skill keeps this file in its web/ folder.
FOREMAN_ROOT = REPO_ROOT / 'foreman' if (REPO_ROOT / 'foreman' / 'lib').is_dir() else REPO_ROOT.parent
sys.path.insert(0, str(FOREMAN_ROOT))
from lib.board import TaskBoard  # noqa: E402
from lib.config import ExecutionConfig  # noqa: E402
from lib.executor import TaskExecutor  # noqa: E402
from lib.store import (  # noqa: E402
    ManagedTaskError,
    dependency_ids,
    dependency_satisfied,
    find_task,
    read_tasks_document,
)
from lib.team import audit_runs, check_team  # noqa: E402

from web_projects import ProjectError, ProjectRegistry  # noqa: E402

EDITABLE_STATUSES = frozenset({
    'PENDING', 'OPEN', 'TODO', 'IN_PROGRESS', 'AWAITING_REVIEW',
    'AWAITING_INTEGRATION', 'REJECTED', 'BLOCKED', 'FAILED',
})
VALID_STATUSES = EDITABLE_STATUSES | {'DONE', 'VERIFIED'}
SPEC_DIR = 'planning/specs'
SPEC_NAME = re.compile(r'[^./\\\x00][^/\\\x00]*\.md')
SPEC_TITLE = re.compile(r'\s{0,3}#\s+(.+?)\s*$')
SPEC_MAX_BYTES = 1024 * 1024


def create_app(repo_root=None, registry_file=None):
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    registry = ProjectRegistry(root, registry_file)
    app = Flask(__name__)
    app.config.update(TASK_FILE=str(root / 'planning/tasks.json'),
                      HISTORY_DIR=str(root / '.task-management/history'),
                      PROJECT_REGISTRY=str(registry.file), MAX_CONTENT_LENGTH=65536)
    app.extensions['projects'] = registry
    # Serialize read/modify/write updates without changing the process working directory.
    update_lock = threading.RLock()

    @app.before_request
    def check_origin():
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            origin = request.headers.get('Origin')
            if origin:
                try:
                    parsed = urlsplit(origin)
                    same_origin = parsed.scheme == request.scheme and parsed.netloc == request.host
                except ValueError:
                    same_origin = False
                if not same_origin:
                    abort(403, description='跨站修改请求已拒绝')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                abort(403, description='跨站修改请求已拒绝')

    def checked_project(project_id):
        project = registry.get(project_id)
        project.validate_data()
        return project

    def document(project):
        doc = read_tasks_document(project.task_file, migrate=False)
        if not isinstance(doc, dict) or not isinstance(doc.get('tasks'), list):
            raise ValueError('Invalid task document')
        if any(not isinstance(task, dict) or not isinstance(task.get('id'), str) for task in doc['tasks']):
            raise ValueError('Invalid task')
        return doc

    def configuration(project):
        # A malformed file makes ExecutionConfig raise, which the catch-all handler reports as a 500.
        config = ExecutionConfig(project.root)
        project.validate_roles(config.get_roles())
        return config

    def row_for(task, tasks):
        return dict(id=task['id'], title=task.get('title', ''),
                    status=task.get('status', 'PENDING'),
                    integration='confirmed' if task.get('status') == 'DONE' and task.get('integration') else 'pending',
                    waiting=[dep for dep in dependency_ids(task.get('dependencies'))
                             if not dependency_satisfied(tasks, dep)])

    def task_view(task, tasks, config):
        role = config.get_role(task.get('role')) or {}
        return dict(task, model=role.get('model'), droid=role.get('droid'),
                    board={key: value for key, value in row_for(task, tasks).items()
                           if key in ('integration', 'waiting')})

    def checkpoint_view(project):
        path = project.path('.task-management/checkpoint.json')
        if not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding='utf-8'))
        data = loaded.get('data', {}) if isinstance(loaded, dict) else None
        if not isinstance(data, dict):
            raise ValueError('Invalid checkpoint')

        def text(value):
            return value if isinstance(value, str) else None

        def count(value):
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        spec = PurePosixPath(text(data.get('spec_file')) or '')
        # Notes and other free-form fields can hold anything; only the cursor fields are shown.
        return dict(phase=text(loaded.get('phase')), timestamp=text(loaded.get('timestamp')),
                    current_task=text(data.get('current_task')),
                    completed_tasks=count(data.get('completed_tasks')),
                    total_tasks=count(data.get('total_tasks')),
                    spec=spec.name if spec.parent == PurePosixPath(SPEC_DIR) and SPEC_NAME.fullmatch(spec.name) else None)

    def spec_files(project):
        directory = project.path(SPEC_DIR)
        if not directory.is_dir():
            return []
        # A link inside specs/ must not expose another file, even one inside the project.
        return [path for path in directory.glob('*.md')
                if SPEC_NAME.fullmatch(path.name) and project.path(path) == path and path.is_file()]

    def spec_file(project, name):
        path = project.path(SPEC_DIR) / name
        if not SPEC_NAME.fullmatch(name) or project.path(path) != path or not path.is_file():
            abort(404, description='Spec not found')
        return path

    def spec_summary(path):
        with path.open('rb') as handle:
            head = handle.read(8192).decode('utf-8', errors='replace')
        title = next((match.group(1) for match in map(SPEC_TITLE.match, head.splitlines()) if match), path.stem)
        stat = path.stat()
        return dict(name=path.name, title=title, size=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat())
    def lookup(doc, task_id):
        task = find_task(doc, task_id)
        if task is None:
            abort(404, description='Task not found')
        return task

    def page_context(project):
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
        app.logger.error('Request failed; details withheld from the web monitor')
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
        project = checked_project(project_id)
        doc, config = document(project), configuration(project)
        return jsonify(success=True, tasks=[task_view(task, doc['tasks'], config) for task in doc['tasks']])

    @app.get('/api/tasks/<task_id>')
    @app.get('/api/projects/<project_id>/tasks/<task_id>')
    def get_task(task_id, project_id='default'):
        project = checked_project(project_id)
        doc = document(project)
        return jsonify(success=True, task=task_view(lookup(doc, task_id), doc['tasks'], configuration(project)))

    @app.put('/api/tasks/<task_id>')
    @app.put('/api/projects/<project_id>/tasks/<task_id>')
    def update_task(task_id, project_id='default'):
        project = checked_project(project_id)
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400, description='Expected a JSON object')
        status = data.get('status')
        if isinstance(status, str) and status in ('DONE', 'VERIFIED'):
            abort(400, description='请通过 foreman 技能 integrate 确认集成并完成任务')
        if not isinstance(status, str) or status not in EDITABLE_STATUSES:
            abort(400, description='Invalid or missing status field')
        if 'reset_retries' in data and not isinstance(data['reset_retries'], bool):
            abort(400, description='reset_retries must be a boolean')
        with update_lock:
            lookup(document(project), task_id)
            board = TaskBoard.load(project.root)
            try:
                board.update_task_status(task_id, status, reset_retries=data.get('reset_retries', False),
                                         require_unmanaged=True)
            except ManagedTaskError:
                abort(409, description='该任务由受管派发维护状态，请在 foreman 技能中用 execution 或 integrate 命令处理')
        return jsonify(success=True, message=f'任务 {task_id} 状态已更新为 {status}')

    @app.get('/api/board')
    @app.get('/api/projects/<project_id>/board')
    def get_board(project_id='default'):
        doc = document(checked_project(project_id))
        rows = [row_for(task, doc['tasks']) for task in doc['tasks']]
        counts = Counter(task.get('status', 'PENDING') for task in doc['tasks'])
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
        project = checked_project(project_id)
        records = []
        for path in project.path('.task-management/history').glob('*.json'):
            record = json.loads(project.path(path).read_text(encoding='utf-8'))
            if not isinstance(record, dict):
                raise ValueError('Invalid history record')
            # Exception text and arbitrary extra fields can contain credentials.
            records.append({key: record[key] for key in (
                'task_id', 'title', 'start_time', 'end_time', 'duration_seconds',
                'status', 'droid', 'model', 'complexity',
            ) if key in record})
        records.sort(key=lambda record: record.get('start_time') or '', reverse=True)
        return jsonify(success=True, history=records)

    @app.get('/api/team')
    @app.get('/api/projects/<project_id>/team')
    def get_team(project_id='default'):
        config = configuration(checked_project(project_id))
        roles = {role: {key: entry.get(key, False if key == 'read_only' else None)
                        for key in ('droid', 'model', 'description', 'read_only')}
                 for role, entry in config.get_roles().items()}
        return jsonify(success=True, roles=roles, parallel={
            'max_parallel': config.get_max_parallel(), 'max_retries': config.get_max_retries(),
        })

    @app.get('/api/team/check')
    @app.get('/api/projects/<project_id>/team/check')
    def get_team_check(project_id='default'):
        project = checked_project(project_id)
        configuration(project)
        checks = check_team(project.root)
        return jsonify(success=True, checks=[
            {key: entry[key] for key in ('role', 'droid', 'model', 'ok', 'problems')} for entry in checks
        ])

    @app.get('/api/team/audit')
    @app.get('/api/projects/<project_id>/team/audit')
    def get_team_audit(project_id='default'):
        project = checked_project(project_id)
        configuration(project)
        return jsonify(success=True, records=[
            {key: entry[key] for key in ('session_id', 'title', 'role', 'expected', 'actual', 'ok')}
            for entry in audit_runs(project.root)
        ])

    @app.get('/api/batch')
    @app.get('/api/projects/<project_id>/batch')
    def get_batch(project_id='default'):
        project = checked_project(project_id)
        document(project)
        configuration(project)
        plan = TaskExecutor(project.root).plan_batch()
        return jsonify(success=True, batch=[
            {key: entry[key] for key in ('task_id', 'task_title', 'role', 'droid', 'model', 'complexity', 'files')}
            for entry in plan['batch']
        ], skipped=[{key: entry[key] for key in ('id', 'reason')} for entry in plan['skipped']])

    @app.get('/api/checkpoint')
    @app.get('/api/projects/<project_id>/checkpoint')
    def get_checkpoint(project_id='default'):
        return jsonify(success=True, checkpoint=checkpoint_view(checked_project(project_id)))

    @app.get('/api/graph')
    @app.get('/api/projects/<project_id>/graph')
    def get_graph(project_id='default'):
        doc = document(checked_project(project_id))
        nodes = [dict(row_for(task, doc['tasks']), role=task.get('role')) for task in doc['tasks']]
        edges, missing = [], []
        for task in doc['tasks']:
            for dep in dict.fromkeys(str(dep) for dep in dependency_ids(task.get('dependencies'))):
                source = find_task(doc, dep)
                if source is None:
                    missing.append({'task': task['id'], 'dependency': dep})
                elif source is not task and {'from': source['id'], 'to': task['id']} not in edges:
                    edges.append({'from': source['id'], 'to': task['id']})
        return jsonify(success=True, nodes=nodes, edges=edges, missing=missing)

    @app.get('/api/specs')
    @app.get('/api/projects/<project_id>/specs')
    def get_specs(project_id='default'):
        specs = [spec_summary(path) for path in spec_files(checked_project(project_id))]
        specs.sort(key=lambda spec: (spec['modified'], spec['name']), reverse=True)
        return jsonify(success=True, specs=specs)

    @app.get('/api/specs/<name>')
    @app.get('/api/projects/<project_id>/specs/<name>')
    def get_spec(name, project_id='default'):
        path = spec_file(checked_project(project_id), name)
        with path.open('rb') as handle:
            raw = handle.read(SPEC_MAX_BYTES + 1)
        return jsonify(success=True, spec=dict(
            spec_summary(path), content=raw[:SPEC_MAX_BYTES].decode('utf-8', errors='replace'),
            truncated=len(raw) > SPEC_MAX_BYTES))
    @app.get('/')
    @app.get('/project/<project_id>/tasks')
    def index(project_id='default'):
        return render_template('index.html', **page_context(checked_project(project_id)))

    @app.get('/task/<task_id>')
    @app.get('/project/<project_id>/task/<task_id>')
    def task_detail(task_id, project_id='default'):
        project = checked_project(project_id)
        lookup(document(project), task_id)
        return render_template('task_detail.html', task_id=task_id, **page_context(project))

    @app.get('/team')
    @app.get('/project/<project_id>/team')
    def team(project_id='default'):
        return render_template('team.html', **page_context(checked_project(project_id)))

    @app.get('/overview')
    @app.get('/project/<project_id>/overview')
    def overview(project_id='default'):
        return render_template('overview.html', **page_context(checked_project(project_id)))
    return app


app = create_app()


def main(argv=None):
    parser = argparse.ArgumentParser(description='foreman 的本地 Web 看板，只监听 127.0.0.1')
    parser.add_argument('port', nargs='?', type=int, default=5001, help='端口，默认 5001')
    parser.add_argument('--project', help='默认项目的根目录（默认是本文件所在的目录）；登记记录也保存在它的 .task-management/ 下')
    parser.add_argument('--quiet', action='store_true', help='不逐条打印请求日志')
    args = parser.parse_args(argv)
    served = create_app(args.project) if args.project else app
    if args.quiet:
        # The pages poll every few seconds; one line per request would fill the log of a board left running.
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    print(f'Task Management：http://localhost:{args.port}', flush=True)
    served.run(host='127.0.0.1', port=args.port, debug=False)


if __name__ == '__main__':
    main()
