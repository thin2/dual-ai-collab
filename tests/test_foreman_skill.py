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
REFERENCES = sorted((SKILL / "references").glob("*.md"))
DOCS = ["foreman/SKILL.md", "foreman/README.md", *(f"foreman/references/{path.name}" for path in REFERENCES),
        "docs/web-ui.md", "README.md"]


def frontmatter() -> dict:
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def skill_body() -> str:
    return (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]


def prose(text: str) -> str:
    """A document without its fenced blocks: the part that talks about itself and about other documents."""
    parts = re.split(r"^```.*$", text, flags=re.MULTILINE)
    return "\n".join(parts[::2])


def linked_references(skill_file: Path) -> set:
    return set(re.findall(r"\]\((references/[^)#]+)", skill_file.read_text(encoding="utf-8")))


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
    # The repository is released as this skill, so its package metadata carries the same number.
    declared = re.search(r'^version = "(.+)"$', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    assert declared.group(1) == version


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


def test_skill_file_and_its_references_mention_every_command_an_agent_can_run():
    # An agent following the skill knows only the commands SKILL.md and the files it links to tell it about.
    text = skill_body() + "".join(path.read_text(encoding="utf-8") for path in REFERENCES)
    commands = choices(parser())
    missing = [name for name in commands if not re.search(rf"(foreman |`){re.escape(name)}\b", text)]
    for group in ("execution", "team", "checkpoint", "config"):
        actions = next(action.choices for action in commands[group]._actions if action.dest == "action")
        missing += [f"{group} {name}" for name in actions if not re.search(rf"{group} {name}\b", text)]
    assert not missing


def test_skill_file_is_short_enough_to_be_loaded_whole():
    # The whole body is loaded when the skill is chosen; what only some runs need belongs in references/.
    assert len(skill_body().splitlines()) <= 500


def test_each_reference_is_reached_from_the_skill_file_and_stands_alone():
    assert linked_references(SKILL / "SKILL.md") == {f"references/{path.name}" for path in REFERENCES}
    for path in REFERENCES:
        text = path.read_text(encoding="utf-8")
        opening, *_ = text.split("\n## ", 1)
        assert "读这份文件" in opening, f"{path.name} 开头要写明什么时候读它"
        # A reader sent from one reference to another reads the second in part; SKILL.md is the only index.
        assert not re.search(r"\]\(|references/", prose(text)), f"{path.name} 不能链接到别的文件"
        sections = re.findall(r"^## (.+)$", prose(text), re.MULTILINE)
        if len(text.splitlines()) > 100:
            assert sections[0] == "目录", f"{path.name} 超过 100 行，开头要有目录"
            contents = text.split("\n## 目录\n", 1)[1].split("\n## ", 1)[0]
            assert re.findall(r"^\d+\. (.+)$", contents, re.MULTILINE) == sections[1:], path.name


def test_section_numbers_in_the_text_name_sections_that_exist():
    numbered = set(re.findall(r"^#{3,4} (\d(?:\.\d)?)[. ]", skill_body(), re.MULTILINE))
    cited = {}
    for name, text in [("SKILL.md", skill_body()), *((path.name, path.read_text(encoding="utf-8")) for path in REFERENCES)]:
        for sub, top in re.findall(r"(?:见|按|在|的) (\d\.\d)(?![\d.])|第 (\d) 节", prose(text)):
            cited.setdefault(sub or top, name)
    assert not {number: name for number, name in cited.items() if number not in numbered}
    assert len(cited) >= 8, "the scan no longer finds the section numbers in the text"


def test_links_between_documents_point_at_files_that_exist():
    broken = []
    for doc in [*DOCS, "CONTRIBUTING.md"]:
        for target in re.findall(r"\]\(([^)#\s]+)", prose((ROOT / doc).read_text(encoding="utf-8"))):
            if "://" not in target and not (ROOT / doc).parent.joinpath(target).exists():
                broken.append(f"{doc}: {target}")
    assert not broken


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


def test_installed_copy_has_every_file_the_skill_file_links_to(tmp_path):
    target = tmp_path / "skill"
    installed = subprocess.run([sys.executable, str(ROOT / "install.py"), "--profile", "foreman", "--source", str(ROOT),
                                "--target", str(target)], capture_output=True, text=True)
    assert installed.returncode == 0, installed.stderr
    links = linked_references(target / "SKILL.md")
    assert links and all((target / link).is_file() for link in links)


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
