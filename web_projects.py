"""Project registration and checked data paths, independent of legacy skills."""
from __future__ import annotations

import fcntl
import json
import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class ProjectError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ProjectContext:
    id: str
    name: str
    root: Path

    def path(self, relative):
        try:
            if not self.root.is_dir() or self.root.resolve() != self.root:
                raise ProjectError('项目目录不存在或不可访问，请检查原路径', 409)
            resolved = (self.root / relative).resolve()
            resolved.relative_to(self.root)
        except (ValueError, OSError, RuntimeError) as exc:
            raise ProjectError('项目数据路径不能指向仓库之外', 409) from exc
        return resolved

    @property
    def task_file(self):
        # The store resolves tasks.md first, then derives its JSON, lock and temp paths.
        for name in ('tasks.json', 'tasks.md', 'codex-tasks.json'):
            self.path('planning/' + name)
        md = self.path('planning/tasks.md')
        for path in (md, md.with_suffix('.json'), md.with_name('codex-tasks.json')):
            self.path(path)
            self.path(path.with_suffix(path.suffix + '.tmp'))
            self.path(path.with_suffix(path.suffix + '.lock'))
        return md

    def validate_data(self):
        _ = self.task_file
        self.path('.task-management/config.json')
        history = self.path('.task-management/history')
        for path in history.glob('*.json'):
            self.path(path)
        droids = self.path('.factory/droids')
        for path in droids.glob('*.md'):
            self.path(path)

    def validate_roles(self, roles):
        for role in roles:
            if not isinstance(role, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', role):
                raise ProjectError('项目角色配置无效', 409)
            self.path(f'.factory/droids/tm-{role}.md')

    def as_dict(self):
        return dict(id=self.id, name=self.name, path=str(self.root),
                    available=self.root.is_dir() and self.root.resolve() == self.root)


class ProjectRegistry:
    def __init__(self, root, registry_file=None):
        root = Path(root).resolve()
        self.default = ProjectContext('default', root.name, root)
        selected = registry_file or os.environ.get('TASK_MANAGEMENT_PROJECTS_FILE')
        self.file = Path(selected).expanduser().absolute() if selected else root / '.task-management/projects.json'
        self._external = bool(selected)
        self._lock = threading.RLock()

    def _check_file(self):
        if not self._external:
            self.default.path(self.file)
            self.default.path(self.file.with_suffix('.json.lock'))
            self.default.path(self.file.with_suffix('.json.tmp'))

    @contextmanager
    def _registration_lock(self):
        with self._lock:
            self._check_file()
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with self.file.with_suffix('.json.lock').open('a') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def list(self):
        self._check_file()
        projects = [self.default]
        if not self.file.exists():
            return projects
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            entries = data['projects']
            if not isinstance(entries, list):
                raise ValueError('invalid projects')
            seen_ids, seen_paths = {'default'}, {self.default.root}
            for item in entries:
                if not isinstance(item, dict) or not all(
                    isinstance(item.get(key), str) and item[key].strip()
                    for key in ('id', 'name', 'path')
                ):
                    raise ValueError('invalid project')
                if not Path(item['path']).is_absolute() or not re.fullmatch(r'[a-zA-Z0-9_-]+', item['id']):
                    raise ValueError('invalid project path or id')
                # Preserve registered paths so replacing a directory with a symlink is rejected.
                root = Path(item['path'])
                if item['id'] in seen_ids or root in seen_paths:
                    raise ValueError('duplicate project')
                seen_ids.add(item['id'])
                seen_paths.add(root)
                projects.append(ProjectContext(item['id'], item['name'], root))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ProjectError('项目注册表无法读取，请修复配置后重试', 500) from exc
        return projects

    def get(self, project_id):
        project = next((item for item in self.list() if item.id == project_id), None)
        if project is None:
            raise ProjectError('项目未登记', 404)
        return project

    def add(self, name, path):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise ProjectError('项目名称必填，最多 100 个字符')
        if not isinstance(path, str) or not path.strip() or not Path(path).expanduser().is_absolute():
            raise ProjectError('请填写项目目录的绝对路径')
        try:
            root = Path(path).expanduser().resolve(strict=True)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ProjectError('项目目录不存在或不可访问') from exc
        if not root.is_dir():
            raise ProjectError('项目路径必须是目录')
        project = ProjectContext(uuid4().hex, name.strip(), root)
        project.validate_data()
        with self._registration_lock():
            projects = self.list()
            if any(item.root.resolve() == root for item in projects):
                raise ProjectError('这个项目目录已经登记', 409)
            entries = [dict(id=p.id, name=p.name, path=str(p.root)) for p in projects[1:] + [project]]
            content = json.dumps({'version': 1, 'projects': entries}, ensure_ascii=False, indent=2) + '\n'
            temp = self.file.with_suffix('.json.tmp')
            temp.write_text(content, encoding='utf-8')
            temp.replace(self.file)
        return project
