"""Commands that only look, and commands that are refused, leave the directory as they found it."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SKILL = Path(__file__).resolve().parents[1] / "foreman"
sys.path.insert(0, str(SKILL))

import lib.team  # noqa: E402
from lib.history import ExecutionHistory  # noqa: E402

_spec = importlib.util.spec_from_file_location("foreman_cli", SKILL / "tools" / "cli.py")
command_line = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(command_line)

PLAN = {"id": "001", "title": "页面", "description": "实现页面", "files": ["a.txt"], "runtime_dependencies": ["a.txt"],
        "acceptance": [{"id": "copy", "scenario": "打开页面", "expected": "显示中文", "method": "manual"}]}

# Read-only, or with nothing to do. Some of them fail where there is no project or no task 001; none may write.
LOOKS = [
    "", "--version", "doctor", "doctor --json", "show", "show 001", "show 999", "show --json", "show --mermaid",
    "status", "select", "batch", "batch --json", "validate", "validate --json", "plan-execution 001",
    "plan-execution 001 --json", "acceptance 001", "history", "history --task-id 001", "execution recover",
    "execution inspect 001", "checkpoint check", "config show", "models", "team show", "team show --json",
    "team check", "team audit", "team remove nobody", "delivery --paths a.txt", "web", "web status", "web --json",
    "web stop",
]
# Refused wherever they are run: there is no task 999, and the rest is input no project accepts.
REFUSED = [
    "nosuchcommand", "update 999 DONE", "update 001 bogus", "fail 999", "integrate 999 --commit HEAD",
    "add --file nowhere.json", "add --file bad.json", "checkpoint save", "config set bogus=1",
    "config set parallel.max_parallel=abc", "team set x --model no-such-model --description d",
    "acceptance 999", "acceptance 999 --template", "plan-execution 999", "run 999 --dispatcher no-such-model",
    "preflight --dispatcher no-such-model", "execution begin 999", "execution finish 999 --outcome completed",
    "execution inspect 999", "execution audit 999", "execution accept 999 --evidence-file nowhere.json",
    "execution retry 999 --reason x", "execution block 999 --reason x", "execution unblock 999 --reason x",
    "execution pause 999 --reason x", "execution track 999 --pid 1 --label x", "integrate 999 --no-git --note x",
    "integrate 001", "integrate 001 --commit HEAD --no-git", "web restart",
]
# Refused once task 001 is on the board but has not been started.
NOT_STARTED = ["add --file plan.json", "execution finish 001 --outcome completed", "execution retry 001 --reason x",
               "execution pause 001 --reason x", "execution track 001 --pid 1 --label x",
               "integrate 001 --no-git --note x"]
# Refused by the board once task 001 is in progress.
MANAGED = ["add --file plan.json", "update 001 DONE", "fail 001"]
# Refused by the workflow while task 001 is in progress. It takes its lock before it can tell,
# so in a clone without lock files these create that file, as an accepted command does.
IN_PROGRESS = [
    "execution begin 001", "execution finish 001 --outcome returned", "execution accept 001 --evidence-file bad.json",
    "execution retry 001 --reason x", "execution unblock 001 --reason x", "integrate 001 --commit HEAD",
    "execution pause 001 --reason x", "integrate 001 --no-git --note x",
]


@pytest.fixture(autouse=True)
def no_models_or_sessions_of_the_developer(monkeypatch, tmp_path):
    monkeypatch.setattr(lib.team, "DEFAULT_SETTINGS", tmp_path / "home" / "settings.json")
    monkeypatch.setattr(lib.team, "DEFAULT_SESSIONS", tmp_path / "home" / "sessions")


def foreman(command: str) -> int:
    """The exit code of one command, run in the current directory by the code bin/foreman runs."""
    output = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(sys, "argv", ["foreman", *shlex.split(command)]))
        stack.enter_context(contextlib.redirect_stdout(output))
        stack.enter_context(contextlib.redirect_stderr(output))
        try:
            command_line.main()
        except SystemExit as stop:
            return stop.code if isinstance(stop.code, int) else int(stop.code is not None)
    return 0


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)


def empty(root: Path) -> None:
    pass


def repository(root: Path) -> None:
    """A git repository with one commit and nothing of foreman's in it."""
    (root / "a.txt").write_text("a", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "a.txt")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")


def planned(root: Path) -> None:
    """A project whose one task has not been started."""
    repository(root)
    (root / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    assert foreman("init") == 0 and foreman("add --file plan.json") == 0


def board_only(root: Path) -> None:
    """A clone of that project when only planning/ was committed."""
    planned(root)
    shutil.rmtree(root / ".task-management")
    (root / "planning" / "tasks.json.lock").unlink()


def started(root: Path) -> None:
    planned(root)
    assert foreman("execution begin 001") == 0


def started_clone(root: Path) -> None:
    """A clone of a project in progress: its records were committed, its lock files ignored as the skill advises."""
    started(root)
    (root / "planning" / "tasks.json.lock").unlink()
    (root / ".task-management" / "workflow.lock").unlink()


SCENARIOS = {
    "empty": (empty, []),
    "repository": (repository, []),
    "planned": (planned, NOT_STARTED),
    "board-only": (board_only, NOT_STARTED),
    "started": (started, MANAGED + IN_PROGRESS),
    "started-clone": (started_clone, MANAGED),
}


def contents(base: Path) -> dict:
    """Every path under base: a folder, a lock file, or a file with its size and the time it was last written."""
    found = {}
    for path in base.rglob("*"):
        relative = path.relative_to(base)
        if ".git" in relative.parts:
            continue
        if path.is_dir():
            found[relative.as_posix()] = "folder"
        elif path.suffix == ".lock":
            # Taking a lock rewrites its file; only whether the file exists says anything.
            found[relative.as_posix()] = "lock"
        else:
            found[relative.as_posix()] = (path.stat().st_size, path.stat().st_mtime_ns)
    return found


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_looking_and_being_refused_change_nothing(scenario, tmp_path, monkeypatch):
    build, refused_here = SCENARIOS[scenario]
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.chdir(root)
    build(root)
    (root / "bad.json").write_text('{"tasks": [{"id": "bad id!", "title": "x"}]}', encoding="utf-8")
    before = contents(tmp_path)
    problems = []
    for command in LOOKS + REFUSED + refused_here:
        code = foreman(command)
        after = contents(tmp_path)
        if command not in LOOKS and code == 0:
            problems.append(f"foreman {command}: was not refused")
        if after != before:
            created, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
            rewritten = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
            problems.append(f"foreman {command}: created {created}, removed {removed}, rewrote {rewritten}")
            before = after
    assert not problems, "\n".join(problems)


def test_the_command_itself_leaves_an_unrelated_directory_empty(tmp_path):
    # Each of these used to create planning/ or .task-management/ wherever it was typed.
    (tmp_path / "home").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for command in (["history"], ["update", "999", "DONE"], ["execution", "begin", "999"]):
        subprocess.run([sys.executable, str(SKILL / "bin" / "foreman"), *command], cwd=elsewhere, capture_output=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "home")})
        assert list(elsewhere.iterdir()) == [], command


def test_history_folder_appears_with_the_first_record(tmp_path):
    history = ExecutionHistory(tmp_path)
    assert history.get_all_history() == [] and history.get_task_history("001") == []
    assert list(tmp_path.iterdir()) == []
    history.record_start("001", "worker", "medium")
    assert len(history.get_all_history()) == 1
