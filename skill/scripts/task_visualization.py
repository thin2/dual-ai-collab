#!/usr/bin/env python3
"""Dependency reports using the task store's canonical ids and dependencies."""
from __future__ import annotations

import json
from html import escape

from tasks_store import CliError, dependency_ids, find_task, read_tasks_document


def _graph(document):
    graph = {}
    for task in document.get('tasks', []):
        graph[task['id']] = []
        for dep in dependency_ids(task.get('dependencies')):
            target = find_task(document, dep)
            graph[task['id']].append(target['id'] if target else dep)
    return graph


def detect_circular_dependencies(tasks):
    graph = _graph(tasks)
    visited, active, cycles = set(), [], []

    def visit(node):
        if node in active:
            cycles.append(active[active.index(node):] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        active.append(node)
        for dep in graph.get(node, []):
            visit(dep)
        active.pop()

    for node in graph:
        visit(node)
    return cycles


def _paths(tasks):
    graph = _graph(tasks)
    if detect_circular_dependencies(tasks):
        raise CliError('任务板存在循环依赖，无法计算依赖层级')
    missing = sorted({dep for deps in graph.values() for dep in deps if dep not in graph})
    if missing:
        raise CliError('依赖任务不存在: ' + ', '.join(missing))
    paths = {}

    def visit(node):
        if node not in paths:
            prefix = max((visit(dep) for dep in graph[node]), key=len, default=[])
            paths[node] = prefix + [node]
        return paths[node]

    for node in graph:
        visit(node)
    return paths


def find_critical_path(tasks):
    return max(_paths(tasks).values(), key=len, default=[])


def find_parallel_tasks(tasks):
    paths = _paths(tasks)
    groups = {}
    for task in tasks.get('tasks', []):
        if task.get('status') == 'OPEN':
            groups.setdefault(len(paths[task['id']]), []).append(task['id'])
    return [groups[level] for level in sorted(groups)]


def _generate_mermaid(tasks):
    lines = ['graph TD']
    for task in tasks.get('tasks', []):
        node = task['id']
        title = escape(task.get('title', node), quote=True).replace('\n', ' ')
        style = {'DONE': 'done', 'VERIFIED': 'done', 'IN_PROGRESS': 'progress', 'FAILED': 'failed'}.get(task.get('status'))
        lines.append(f'    t{node}["{node}: {title}"]' + (f':::{style}' if style else ''))
    for node, deps in _graph(tasks).items():
        lines.extend(f'    t{dep} --> t{node}' for dep in deps)
    lines += ['    classDef done fill:#90EE90', '    classDef progress fill:#FFD700', '    classDef failed fill:#FF6B6B']
    return '\n'.join(lines)


def _generate_dot(tasks):
    lines = ['digraph TaskDependencies {', '    rankdir=LR;', '    node [shape=box];']
    for task in tasks.get('tasks', []):
        label = json.dumps(f"{task['id']}: {task.get('title', '')}", ensure_ascii=False)
        color = {'DONE': 'lightgreen', 'VERIFIED': 'lightgreen', 'IN_PROGRESS': 'yellow', 'FAILED': 'red'}.get(task.get('status'), 'lightgray')
        lines.append(f'    "{task["id"]}" [label={label}, fillcolor={color}, style=filled];')
    for node, deps in _graph(tasks).items():
        lines.extend(f'    "{dep}" -> "{node}";' for dep in deps)
    return '\n'.join(lines + ['}'])


def generate_dependency_graph(output_format='mermaid'):
    tasks = read_tasks_document()
    if output_format == 'mermaid':
        return _generate_mermaid(tasks)
    if output_format == 'dot':
        return _generate_dot(tasks)
    raise CliError(f'不支持的格式: {output_format}')


def generate_analysis_report():
    tasks = read_tasks_document()
    lines = ['# 任务依赖分析报告']
    cycles = detect_circular_dependencies(tasks)
    if cycles:
        return '\n'.join(lines + ['## 检测到循环依赖'] + [' → '.join(cycle) for cycle in cycles])
    critical = find_critical_path(tasks)
    lines += ['## 最长依赖链', ' → '.join(critical) or '暂无任务', '## OPEN 任务依赖层级（后续层级需等待依赖完成）']
    for index, group in enumerate(find_parallel_tasks(tasks), 1):
        lines.append(f'{index}. ' + ', '.join(group))
    return '\n'.join(lines)
