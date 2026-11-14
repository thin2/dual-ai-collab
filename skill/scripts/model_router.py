#!/usr/bin/env python3
"""Explicit CLI protocols and availability-only fallback routing."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tasks_store import CliError, find_task, read_tasks_document
from structured_logging import log_event
from execution_result import validate_result

DEFAULT_ROUTING = {
    'quick': {'adapter': 'deepseek-cli'},
    'normal': {'adapter': 'claude-cli'},
    'heavy': {'adapter': 'codex'},
}
DEFAULT_FALLBACK = {'deepseek-cli': ['claude-cli', 'codex'], 'claude-cli': ['codex'], 'codex': []}
DEFAULT_COMMANDS = {'codex': ['codex', 'exec', '-'], 'claude-cli': ['claude']}


def _load_routing_config():
    path = Path('.dual-ai-collab/model-routing.json')
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CliError(f'无法读取路由配置: {exc}') from exc
    if not isinstance(config, dict):
        raise CliError('路由配置必须是 JSON 对象')
    for key in ('model_routing', 'fallback_chain', 'adapter_commands', 'adapter_paths', 'adapter_protocols'):
        if key in config and not isinstance(config[key], dict):
            raise CliError(f'{key} 必须是对象')
    for level, route in config.get('model_routing', {}).items():
        if not isinstance(route, dict) or not isinstance(route.get('adapter'), str) or not route['adapter']:
            raise CliError(f'无效的路由规则: {level}')
    for name, chain in config.get('fallback_chain', {}).items():
        if not isinstance(chain, list) or any(not isinstance(item, str) or not item for item in chain):
            raise CliError(f'无效的回退链: {name}')
    return config


def adapter_definition(name, config=None):
    config = _load_routing_config() if config is None else config
    command = config.get('adapter_commands', {}).get(name, DEFAULT_COMMANDS.get(name))
    if command is None:
        # No assumed native protocol for third-party DeepSeek tools.
        return {'adapter': name, 'command': None, 'protocol': None, 'reason': '需要配置兼容包装器'}
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise CliError(f'adapter_commands.{name} 必须是非空字符串数组')
    command = list(command)
    native_claude = Path(command[0]).name in ('claude', 'claude.exe')
    protocol = config.get('adapter_protocols', {}).get(name, 'claude' if native_claude else 'codex')
    if protocol not in ('codex', 'claude'):
        raise CliError(f'不支持的适配器协议: {protocol}')
    override = config.get('adapter_paths', {}).get(name)
    if override is not None:
        if not isinstance(override, str) or not override:
            raise CliError(f'无效的适配器路径: {name}')
        command[0] = str(Path(override).expanduser().resolve())
    return {'adapter': name, 'command': command, 'protocol': protocol, 'reason': ''}


def resolve_adapter_for_task(task_num, execution_level=None):
    config = _load_routing_config()
    try:
        task = find_task(read_tasks_document(), task_num) or {}
    except CliError:
        task = {}
    level = execution_level or task.get('execution_level') or 'normal'
    routing = config.get('model_routing', DEFAULT_ROUTING)
    route = routing.get(level, routing.get('normal'))
    name = task.get('adapter')
    if not name:
        if route is None:
            raise CliError(f'缺少 {level} 或 normal 路由')
        name = route['adapter']
    definition = adapter_definition(name, config)
    definition['reason'] = (route or {}).get('reason', '')
    return definition


def validate_adapter_available(adapter_name):
    command = adapter_definition(adapter_name)['command']
    return bool(command and shutil.which(command[0]))


def resolve_available_adapter(initial, sandbox=None):
    config = _load_routing_config()
    fallback = config.get('fallback_chain', DEFAULT_FALLBACK)
    queue, visited = [initial['adapter']], set()
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        definition = adapter_definition(name, config)
        compatible = (sandbox is None or
                      (definition['protocol'] == 'claude' and sandbox == 'provider-default') or
                      (definition['protocol'] == 'codex' and sandbox != 'provider-default'))
        if compatible and definition['command'] and shutil.which(definition['command'][0]):
            if name != initial['adapter']:
                log_event('adapter_fallback', from_adapter=initial['adapter'], to_adapter=name)
            return definition
        log_event('adapter_unavailable', adapter=name, reason='unavailable' if compatible else 'incompatible_permissions')
        queue.extend(fallback.get(name, []))
    raise CliError('没有可用的适配器满足当前权限模式（已检查: ' + ', '.join(sorted(visited)) + '）；请运行 check-adapters')


def get_fallback_adapter(adapter_name):
    config = _load_routing_config()
    for name in config.get('fallback_chain', DEFAULT_FALLBACK).get(adapter_name, []):
        if name != adapter_name:
            return adapter_definition(name, config)
    return None


def check_adapters():
    config = _load_routing_config()
    names = set(DEFAULT_COMMANDS) | set(config.get('adapter_commands', {}))
    names.update(route['adapter'] for route in config.get('model_routing', DEFAULT_ROUTING).values())
    for name, chain in config.get('fallback_chain', DEFAULT_FALLBACK).items():
        names.add(name)
        names.update(chain)
    result = []
    for name in sorted(names):
        entry = adapter_definition(name, config)
        entry['path'] = shutil.which(entry['command'][0]) if entry['command'] else None
        entry['available'] = bool(entry['path'])
        result.append(entry)
    return result


def build_adapter_command(adapter_config, workdir, *, model=None, effort=None,
                          sandbox='workspace-write', schema_file=None, result_file=None):
    cmd = list(adapter_config['command'])
    protocol = adapter_config.get('protocol', 'codex')
    if protocol == 'claude':
        if sandbox != 'provider-default':
            raise CliError('Claude 原生协议不支持 Codex 沙箱；请选择 Codex 或显式使用 --sandbox provider-default')
        if 'exec' in cmd or '-' in cmd:
            raise CliError('Claude 原生命令应配置为 ["claude"]，不支持 exec -')
        cmd += ['--print', '--output-format', 'json', '--permission-mode', 'default']
        if model:
            cmd += ['--model', model]
        if effort:
            if effort not in ('low', 'medium', 'high', 'xhigh'):
                raise CliError(f'Claude 不支持推理强度: {effort}')
            cmd += ['--effort', effort]
        if schema_file:
            cmd += ['--json-schema', Path(schema_file).read_text(encoding='utf-8')]
        return cmd
    if sandbox == 'provider-default':
        raise CliError('Codex 协议需要明确的沙箱模式，不支持 provider-default')
    cmd = [arg for arg in cmd if arg != '-']
    for flag, value in [('-C', workdir), ('-s', sandbox), ('-m', model),
                        ('-c', f'model_reasoning_effort={effort}' if effort else None),
                        ('--output-schema', schema_file), ('-o', result_file)]:
        if value is not None and flag not in cmd:
            cmd += [flag, value]
    # Codex-compatible wrappers receive the same stdin contract.
    cmd.append('-')
    return cmd




def normalize_claude_output(output_file, result_file=None, schema_file=None):
    try:
        envelope = json.loads(Path(output_file).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CliError(f'Claude 输出不是有效 JSON: {exc}') from exc
    if not isinstance(envelope, dict) or envelope.get('is_error') or envelope.get('permission_denials'):
        raise CliError('Claude 返回执行错误或权限拒绝，详见日志')
    if result_file:
        result = envelope.get('structured_output')
        if not isinstance(result, dict):
            raise CliError('Claude 缺少 structured_output')
        if schema_file:
            validate_result(result, json.loads(Path(schema_file).read_text(encoding="utf-8")))
        from tasks_store import atomic_write
        atomic_write(Path(result_file), json.dumps(result, ensure_ascii=False) + '\n')
