"""Explicit project paths and an atomic registry; never change process cwd."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4

from platform_utils import FileLock
from tasks_store import CliError, atomic_write


class ProjectError(CliError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ProjectContext:
    id: str
    name: str
    root: Path

    def path(self, relative):
        if not self.root.is_dir():
            raise ProjectError('项目目录不存在或不可访问，请检查原路径', 409)
        resolved = (self.root / relative).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ProjectError('项目数据路径不能指向仓库之外', 409) from exc
        return resolved

    @property
    def task_file(self):
        # Check both files, since writes also render Markdown.
        self.path('planning/codex-tasks.md')
        return self.path('planning/tasks.json')

    @property
    def runtime_dir(self):
        return self.path('.dual-ai-collab')

    def as_dict(self):
        return dict(id=self.id, name=self.name, path=str(self.root), available=self.root.is_dir())


class ProjectRegistry:
    def __init__(self, root, registry_file=None):
        root = Path(root).resolve()
        self.default = ProjectContext('default', root.name, root)
        self.file = Path(registry_file).expanduser().resolve() if registry_file else root / '.dual-ai-collab/projects.json'

    def list(self):
        projects = [self.default]
        if not self.file.exists():
            return projects
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            entries = data['projects']
            if not isinstance(entries, list):
                raise ValueError('projects must be a list')
            seen_ids, seen_paths = {'default'}, {self.default.root}
            for item in entries:
                if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ('id', 'name', 'path')):
                    raise ValueError('invalid project entry')
                if not Path(item['path']).is_absolute():
                    raise ValueError('project path must be absolute')
                if any(char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in item['id']):
                    raise ValueError('invalid project id')
                root = Path(item['path']).resolve()
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
        if not project:
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
        project.task_file
        project.runtime_dir
        with FileLock(self.file.with_suffix('.json.lock')):
            projects = self.list()
            if any(item.root == root for item in projects):
                raise ProjectError('这个项目目录已经登记', 409)
            entries = [dict(id=p.id, name=p.name, path=str(p.root)) for p in projects[1:] + [project]]
            atomic_write(self.file, json.dumps({'version': 1, 'projects': entries}, ensure_ascii=False, indent=2) + '\n')
        return project
