"""Integration coverage using a local worker stub, without external AI services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skill/scripts/cli.py'
sys.path.insert(0, str(CLI.parent))
from task_history import get_task_history


def call_cli(tmp_path, *args, no_site=False):
    return subprocess.run(
        [sys.executable, *(['-S'] if no_site else []), str(CLI), *args],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )


def test_core_cli_without_optional_dependencies(tmp_path):
    for args in [('--help',), ('init',), ('templates', 'list'), ('history',)]:
        result = call_cli(tmp_path, *args, no_site=True)
        assert result.returncode == 0, result.stderr
    (tmp_path / 'planning/tasks.json').write_text(json.dumps({'tasks': []}))
    result = call_cli(tmp_path, 'schedule', no_site=True)
    assert result.returncode == 1
    assert 'psutil' in result.stderr
    assert 'Traceback' not in result.stderr


@pytest.mark.skipif(os.name == 'nt', reason='stub uses Unix shebang')
@pytest.mark.parametrize('backend', ['direct', 'adapter'])
def test_execute_verify_and_complete(tmp_path, monkeypatch, backend):
    monkeypatch.chdir(tmp_path)
    assert call_cli(tmp_path, 'init').returncode == 0
    stub = tmp_path / 'worker'
    stub.write_text('#!' + sys.executable + '\n' + '''import json, pathlib, sys
sys.stdin.read()
pathlib.Path('artifact.txt').write_text('verified')
args = sys.argv[1:]
if '-o' in args:
    pathlib.Path(args[args.index('-o') + 1]).write_text(json.dumps({
        'result': 'DONE', 'summary': 'ok', 'files_changed': ['artifact.txt'],
        'acceptance': [], 'verification': [], 'notes': []}))
''')
    stub.chmod(0o755)
    monkeypatch.setenv('CODEX_BIN', str(stub))
    (tmp_path / '.dual-ai-collab/model-routing.json').write_text(json.dumps({
        'model_routing': {'normal': {'adapter': 'stub'}},
        'adapter_commands': {'stub': [str(stub)]},
    }))
    board = tmp_path / 'planning/codex-tasks.md'
    board.write_text('''## 任务 #001: integration

**状态**: OPEN
**执行级别**: normal
**模型**: test-model

### 验收标准
```bash
''' + f'''"{sys.executable}" -c "from pathlib import Path; assert Path('artifact.txt').read_text() == 'verified'"
```

---
''')
    result = call_cli(tmp_path, 'run', 'start', '001', 'create artifact', '--backend', backend)
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 15
    history = []
    while time.monotonic() < deadline:
        history = get_task_history('001')
        if history and history[0]['status'] != 'running':
            break
        time.sleep(0.05)
    assert history and history[0]['status'] == 'success'
    assert history[0]['model'] == 'test-model'
    assert history[0]['adapter'] == ('codex' if backend == 'direct' else 'stub')
    assert history[0]['exit_code'] == 0
    assert history[0]['duration_seconds'] >= 0
    # Execution alone must not mark the board DONE.
    assert json.loads((tmp_path / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'OPEN'
    result = call_cli(tmp_path, 'verify', 'run', '001')
    assert result.returncode == 0, result.stderr
    assert 'VERIFY_PASSED' in result.stdout
    assert call_cli(tmp_path, 'update', '001', 'DONE').returncode == 0
    assert json.loads((tmp_path / 'planning/tasks.json').read_text())['tasks'][0]['status'] == 'DONE'
    report = call_cli(tmp_path, 'history')
    assert report.returncode == 0
    assert '成功: 1, 失败: 0' in report.stdout


@pytest.mark.parametrize('outcome, expected', [(0, 'success'), (127, 'failed'), (143, 'stopped')])
def test_worker_history_outcomes(tmp_path, monkeypatch, outcome, expected):
    from task_history import track_execution
    monkeypatch.chdir(tmp_path)
    prompt = tmp_path / 'prompt.txt'
    prompt.write_text('hello')
    for _ in range(2):
        with pytest.raises(SystemExit):
            with track_execution('002', adapter='stub', model=None, prompt_file=str(prompt)):
                raise SystemExit(outcome)
    history = get_task_history('002')
    assert len(history) == 2
    assert all(item['status'] == expected and item['exit_code'] == outcome for item in history)


def test_worker_history_unexpected_exception(tmp_path, monkeypatch):
    from task_history import track_execution
    monkeypatch.chdir(tmp_path)
    with pytest.raises(OSError):
        with track_execution('003', adapter='stub', model=None, prompt_file='missing'):
            raise OSError('test failure')
    history = get_task_history('003')
    assert history[0]['status'] == 'failed'
    assert 'test failure' in history[0]['error_message']
