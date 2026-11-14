from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skill/scripts'))
import model_router
import run_task
from tasks_store import CliError
from task_history import get_task_history
from run_store import read_run_record


def configure(tmp_path, data):
    folder = tmp_path / '.dual-ai-collab'
    folder.mkdir(exist_ok=True)
    (folder / 'model-routing.json').write_text(json.dumps(data))


def test_fallback_visits_all_siblings_and_handles_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configure(tmp_path, {'adapter_commands': {'a': ['missing-a'], 'b': ['missing-b'], 'c': [sys.executable]},
                         'fallback_chain': {'a': ['b', 'c'], 'b': ['a']}})
    resolved = model_router.resolve_available_adapter({'adapter': 'a'})
    assert resolved['adapter'] == 'c'
    configure(tmp_path, {'adapter_commands': {'a': ['missing-a'], 'b': ['missing-b']},
                         'fallback_chain': {'a': ['b'], 'b': ['a']}})
    with pytest.raises(CliError, match='没有可用'):
        model_router.resolve_available_adapter({'adapter': 'a'})


def test_path_override_is_used_for_check_and_execution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configure(tmp_path, {'adapter_commands': {'x': ['missing']}, 'adapter_paths': {'x': sys.executable}})
    assert model_router.validate_adapter_available('x')
    assert model_router.adapter_definition('x')['command'][0] == str(Path(sys.executable).resolve())


def test_claude_has_native_arguments_and_explicit_permissions(tmp_path):
    schema = tmp_path / 'schema.json'
    schema.write_text(json.dumps(run_task.RESULT_SCHEMA))
    config = {'adapter': 'claude-cli', 'command': ['claude'], 'protocol': 'claude'}
    with pytest.raises(CliError, match='沙箱'):
        model_router.build_adapter_command(config, str(tmp_path))
    cmd = model_router.build_adapter_command(config, str(tmp_path), sandbox='provider-default',
                                            model='test', effort='high', schema_file=str(schema), result_file='r.json')
    assert '--json-schema' in cmd and '--print' in cmd
    assert '--model' in cmd and '--effort' in cmd
    assert cmd[cmd.index('--permission-mode') + 1] == 'default'
    assert not {'-C', '-s', '-c', '-o', 'exec', '-'}.intersection(cmd)


@pytest.mark.skipif(os.name == 'nt', reason='Unix stub')
@pytest.mark.parametrize('mode', ['ok', 'invalid', 'denied', 'bad-schema'])
def test_native_claude_envelope_worker(tmp_path, monkeypatch, mode):
    monkeypatch.chdir(tmp_path)
    stub = tmp_path / 'claude-stub'
    envelope = {'is_error': False, 'structured_output': {
        'result': 'DONE', 'summary': 'native ok', 'files_changed': [],
        'acceptance': [], 'verification': [], 'notes': []}}
    if mode == 'bad-schema':
        envelope['structured_output'] = {'result': 'DONE'}
    if mode == 'denied':
        envelope['permission_denials'] = [{'tool_name': 'Bash'}]
    output = json.dumps(envelope) if mode != 'invalid' else 'not-json'
    stub.write_text('#!' + sys.executable + '\n' +
                    'import sys\nargs = sys.argv[1:]\n' +
                    'assert "--print" in args and "--json-schema" in args\n' +
                    'assert not {"-C", "-s", "-o", "exec"}.intersection(args)\n' +
                    'assert sys.stdin.read() == "hello"\n' +
                    'sys.stderr.write("provider stderr\\n")\n' +
                    'print(' + repr(output) + ')\n')
    stub.chmod(0o755)
    configure(tmp_path, {'model_routing': {'normal': {'adapter': 'native'}},
                         'adapter_commands': {'native': [str(stub)]},
                         'adapter_protocols': {'native': 'claude'}})
    run_task.cmd_start('001', 'hello', 'adapter', str(tmp_path), sandbox='provider-default')
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        history = get_task_history('001')
        if history and history[0]['status'] != 'running':
            break
        time.sleep(0.05)
    assert history[0]['status'] == ('success' if mode == 'ok' else 'failed')
    record = read_run_record('001')
    if mode == 'ok':
        assert json.loads(Path(record['result_file']).read_text())['summary'] == 'native ok'
    else:
        assert not Path(record['result_file']).exists()
    assert 'provider stderr' in Path(record['log_file']).read_text()


def test_invalid_routing_is_not_silently_replaced(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for data in [[], {'fallback_chain': {'x': 'not-a-list'}}, {'model_routing': {'normal': None}}]:
        configure(tmp_path, data)
        with pytest.raises(CliError):
            model_router.check_adapters()


def test_fallback_preserves_sandbox_requirement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configure(tmp_path, {'adapter_commands': {'native': [sys.executable], 'compatible': [sys.executable]},
                         'adapter_protocols': {'native': 'claude', 'compatible': 'codex'},
                         'fallback_chain': {'native': ['compatible']}})
    assert model_router.resolve_available_adapter({'adapter': 'native'}, sandbox='workspace-write')['adapter'] == 'compatible'
    assert model_router.resolve_available_adapter({'adapter': 'native'}, sandbox='provider-default')['adapter'] == 'native'


def test_default_backend_respects_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DUAL_AI_DEFAULT_BACKEND', 'adapter')
    called = []
    monkeypatch.setitem(run_task._BACKEND_DISPATCH, 'adapter', {'start': lambda *args: called.append(args) or {}})
    args = run_task.build_parser().parse_args(['start', '001', 'hello'])
    run_task.dispatch(args)
    assert called
