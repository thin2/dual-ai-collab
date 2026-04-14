from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import verify_task  # noqa: E402


def write_board(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_verify_extract_reads_commands_from_json_backed_task(tmp_path, capsys):
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: 验收任务

**状态**: OPEN

### 验收标准
- [ ] `python -c "print(1)"` 可执行
- [ ] `python -c "print(2)"` 也可执行

---
""",
    )

    assert verify_task.cmd_extract("001", str(board)) == 0
    out = capsys.readouterr().out
    assert 'python -c "print(1)"' in out
    assert 'python -c "print(2)"' in out


def test_verify_run_executes_commands(tmp_path):
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: 验证执行

**状态**: OPEN

### 验收标准
- [ ] `python -c "from pathlib import Path; Path('ok.txt').write_text('ok', encoding='utf-8')"` 生成文件

---
""",
    )

    result = verify_task.cmd_run("001", str(board), str(tmp_path))
    assert result == 0
    assert (tmp_path / "ok.txt").exists()


def test_cli_smoke_summary_command(tmp_path):
    board = tmp_path / "planning" / "codex-tasks.md"
    write_board(
        board,
        """## 任务 #001: CLI 测试

**状态**: OPEN

---
""",
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "skill" / "scripts" / "cli.py"), "summary", str(board)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "总任务: 1" in result.stdout
