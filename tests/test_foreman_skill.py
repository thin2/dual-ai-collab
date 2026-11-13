"""The skill as something people install and follow: its metadata, its documented commands, its self-check."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "foreman"
DOCS = ["foreman/SKILL.md", "foreman/README.md", "foreman/references/managed-workflow.md", "docs/web-ui.md",
        "README.md"]


def frontmatter() -> dict:
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def parser():
    spec = importlib.util.spec_from_file_location("foreman_cli", SKILL / "tools" / "cli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_parser()


def choices(command_parser) -> dict:
    return next(action.choices for action in command_parser._actions if isinstance(action.choices, dict))


def test_frontmatter_routes_and_identifies_the_skill():
    meta = frontmatter()
    assert meta["name"] == SKILL.name == "foreman"
    # The description is all Droid sees when choosing a skill: what it does, when to use it, and when not to.
    assert "适用于" in meta["description"] and "不使用本技能" in meta["description"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])


def test_version_is_what_the_command_and_the_changelog_say():
    version = frontmatter()["version"]
    shown = subprocess.run([str(SKILL / "bin" / "foreman"), "--version"], capture_output=True, text=True)
    assert shown.stdout == f"foreman {version}\n", shown.stderr
    latest = re.search(r"^- \*\*v(\d+\.\d+)\*\*", (ROOT / "README.md").read_text(encoding="utf-8"), re.MULTILINE)
    assert version.startswith(latest.group(1) + ".")


def documented_commands():
    """Each `foreman ...` line of a fenced block and each inline `foreman ...` span, with where it is written."""
    for doc in DOCS:
        fenced, pending = False, ""
        for number, line in enumerate((ROOT / doc).read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("```"):
                fenced = not fenced
            elif not fenced:
                for span in re.findall(r"`(foreman [^`]+)`", line):
                    yield f"{doc}:{number}", span
            else:
                pending += line.strip()
                if pending.endswith("\\"):
                    pending = pending[:-1]
                    continue
                if pending.startswith("foreman "):
                    yield f"{doc}:{number}", pending
                pending = ""


def test_documented_commands_are_accepted_by_the_command_line():
    command_line = parser()
    checked, rejected = 0, []
    for where, command in documented_commands():
        # <名称> stands for a value the reader fills in; a redirect belongs to the shell.
        words = shlex.split(re.sub(r"<[^>]*>", "1", command).split(" > ")[0], comments=True)
        if words[1:] == ["..."]:  # how the docs write "any foreman command"
            continue
        checked += 1
        errors = io.StringIO()
        try:
            with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                command_line.parse_args(words[1:])
        except SystemExit as stop:
            if stop.code:
                rejected.append(f"{where}: {command}\n    {errors.getvalue().strip().splitlines()[-1]}")
    assert not rejected, "\n".join(rejected)
    assert checked > 100, "the scan no longer finds the commands in the docs"


def test_skill_file_mentions_every_command_an_agent_can_run():
    # An agent following the skill knows only the commands SKILL.md tells it about.
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    commands = choices(parser())
    missing = [name for name in commands if not re.search(rf"(foreman |`){re.escape(name)}\b", text)]
    for group in ("execution", "team", "checkpoint", "config"):
        actions = next(action.choices for action in commands[group]._actions if action.dest == "action")
        missing += [f"{group} {name}" for name in actions if not re.search(rf"{group} {name}\b", text)]
    assert not missing


def task(task_id, **fields):
    return {"id": task_id, "title": "页面", "description": "实现页面", "files": [f"page-{task_id}.txt"],
            "runtime_dependencies": [f"page-{task_id}.txt"],
            "acceptance": [{"id": "copy", "scenario": "打开页面", "expected": "显示中文", "method": "manual"}],
            **fields}


def cli(root, *args):
    # A private HOME and a bare PATH: no droid, no models and no foreman link of the user's own.
    return subprocess.run([sys.executable, str(SKILL / "tools" / "cli.py"), *args], cwd=root, capture_output=True,
                          text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(root.parent / "home")})


def add(root, name, content):
    (root / name).write_text(json.dumps(content), encoding="utf-8")
    return cli(root, "add", "--file", name)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "home").mkdir()
    assert cli(root, "init").returncode == 0
    assert add(root, "plan.json", task("001")).returncode == 0
    return root


def files_under(folder):
    return {str(path.relative_to(folder)): path.stat().st_mtime_ns for path in folder.rglob("*")}


def test_doctor_reports_a_usable_project_and_writes_nothing(project):
    before = files_under(project.parent)
    checked = cli(project, "doctor")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert f"[正常] 技能: foreman {frontmatter()['version']}" in checked.stdout
    assert "[正常] 任务板: 1 个任务：PENDING 1" in checked.stdout
    # Neither droid nor models exist here, which matters only once a task names a role.
    assert "[注意] droid" in checked.stdout and "[注意] 模型配置" in checked.stdout
    assert "[问题]" not in checked.stdout
    assert files_under(project.parent) == before
    assert not (project / ".task-management" / "history").exists()


def test_doctor_outside_a_project_says_so_and_creates_nothing(tmp_path):
    (tmp_path / "home").mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    checked = cli(empty, "doctor")
    assert checked.returncode == 0 and checked.stderr == "", checked.stderr
    assert "[注意] 项目" in checked.stdout and "foreman init" in checked.stdout
    assert list(empty.iterdir()) == []


def test_doctor_names_every_file_that_cannot_be_used(project):
    started = json.loads(cli(project, "execution", "begin", "001").stdout)["execution_id"]
    state = project / ".task-management"
    record = state / "history" / f"{started}.json"
    record.write_text("{", encoding="utf-8")
    (state / "config.json").write_text("[]", encoding="utf-8")
    (state / "checkpoint.json").write_text("{", encoding="utf-8")
    checked = cli(project, "doctor", "--json")
    report = json.loads(checked.stdout)
    assert checked.returncode == 1 and report["ok"] is False
    problems = {item["name"]: item["detail"] for item in report["items"] if item["level"] == "problem"}
    assert set(problems) == {"配置", "checkpoint", "执行记录"}
    assert record.name in problems["执行记录"] and "config.json" in problems["配置"]
    record.unlink()
    assert f"任务板登记的记录不存在：任务 001 的 {started}" in cli(project, "doctor").stdout


def test_doctor_requires_the_dispatch_tools_once_a_task_names_a_role(project):
    assert add(project, "role.json", task("002", role="backend")).returncode == 0
    checked = cli(project, "doctor")
    assert checked.returncode == 1
    for name in ("droid", "模型配置", "角色"):
        assert f"[问题] {name}: " in checked.stdout
    assert "未完成的任务要派给角色 backend" in checked.stdout


def test_add_lists_what_the_tasks_it_wrote_still_lack(project):
    added = add(project, "thin.json", {"id": "003", "title": "只有标题", "dependencies": ["009"]})
    assert added.returncode == 0 and "已写入 1 个任务: 003" in added.stdout, added.stderr
    for problem in ("003 files:", "003 runtime_dependencies:", "003 acceptance:", "003 description:",
                    "003 dependencies: 依赖的任务 #009 不存在"):
        assert problem in added.stdout
    # What earlier tasks lack is for validate to report, not for this add.
    complete = add(project, "full.json", task("004"))
    assert complete.returncode == 0 and "要在执行前补齐" not in complete.stdout


def test_installer_reports_the_version_it_installs_and_the_one_it_replaces(tmp_path):
    version = frontmatter()["version"]
    target = tmp_path / "skill"

    def install(*extra):
        return subprocess.run([sys.executable, str(ROOT / "install.py"), "--profile", "foreman", "--source", str(ROOT),
                               "--target", str(target), *extra], capture_output=True, text=True)

    first = install()
    assert first.returncode == 0 and f"version: {version}\n" in first.stdout, first.stderr
    assert f"version: {version}（替换了 {version}）\n" in install("--force").stdout
    shown = subprocess.run([str(target / "bin" / "foreman"), "--version"], capture_output=True, text=True)
    assert shown.stdout == f"foreman {version}\n", shown.stderr
    # A copy installed before versions were recorded.
    skill_file = target / "SKILL.md"
    skill_file.write_text(skill_file.read_text(encoding="utf-8").replace(f"version: {version}\n", ""), encoding="utf-8")
    assert f"version: {version}（替换了没有版本号的旧版）\n" in install("--force").stdout


def as_windows(program, *args, cwd):
    """Start a program the way Windows does: sys.platform already says win32 when its first line runs."""
    # flask and subprocess load first; imported under win32 they look for Windows modules this machine lacks.
    code = ("import runpy, subprocess, sys\nimport flask\nsys.platform = 'win32'\nsys.argv = sys.argv[1:]\n"
            "runpy.run_path(sys.argv[0], run_name='__main__')")
    # The timeout is for the web server: without its check it would start and serve until killed.
    return subprocess.run([sys.executable, "-c", code, str(ROOT / program), *args], cwd=cwd, capture_output=True,
                          text=True, timeout=30)


@pytest.mark.parametrize("program", [
    ("foreman/bin/foreman", "status"),
    ("foreman/tools/cli.py", "init"),
    ("web_server.py", "5999"),
    ("install.py", "--target", "skill"),
])
def test_windows_is_told_once_that_only_macos_and_linux_are_supported(program, tmp_path):
    refused = as_windows(*program, cwd=tmp_path)
    assert refused.returncode == 1 and refused.stdout == "", refused.stdout + refused.stderr
    # Also in English: a console that cannot show Chinese is likeliest on the system this message is for.
    assert "只支持 macOS 和 Linux" in refused.stderr and "macOS and Linux only" in refused.stderr
    assert "WSL" in refused.stderr and "Traceback" not in refused.stderr
    assert list(tmp_path.iterdir()) == []


def test_windows_can_still_install_the_legacy_skill(tmp_path):
    installed = as_windows("install.py", "--profile", "full", "--source", str(ROOT), "--target", "skill", cwd=tmp_path)
    assert installed.returncode == 0, installed.stderr
    assert (tmp_path / "skill" / "SKILL.md").is_file()
