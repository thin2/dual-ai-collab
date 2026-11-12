"""What the CLI says when something is wrong: the file or task involved, why, and what to do next."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "foreman"
sys.path.insert(0, str(SKILL))

from lib.board import TaskBoard  # noqa: E402
from lib.config import ConfigError, ExecutionConfig  # noqa: E402
from lib.workflow import Workflow  # noqa: E402

CHECK = {"id": "copy", "scenario": "打开页面", "expected": "显示中文", "method": "manual"}
TRUNCATED_CONFIG = '{"roles": {"backend": {"droid": "tm-backend", "model": "custom:m"}},\n'


def task(task_id, **fields):
    return {"id": task_id, "title": "页面", "description": "实现页面", "files": [f"page-{task_id}.txt"],
            "runtime_dependencies": [f"page-{task_id}.txt"], "acceptance": [CHECK], **fields}


@pytest.fixture
def project(tmp_path):
    """Task 001 is done by the current session, 002 goes to a role. No droid and no model settings exist."""
    root = tmp_path / "project"
    root.mkdir()
    (tmp_path / "home").mkdir()
    assert cli(root, "init").returncode == 0
    (root / "plan.json").write_text(json.dumps([task("001"), task("002", role="backend")]), encoding="utf-8")
    assert cli(root, "add", "--file", "plan.json").returncode == 0
    return root


def cli(root, *args):
    # A private HOME and a bare PATH keep the user's own models and droid out of the result.
    return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args], cwd=root, capture_output=True,
                          text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(root.parent / "home")})


def refused(result, *fragments):
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.startswith("错误: ") and "Traceback" not in result.stderr, result.stderr
    for fragment in fragments:
        assert fragment in result.stderr, result.stderr


@pytest.mark.parametrize("contents", [TRUNCATED_CONFIG, "[]", '{"roles": []}', '{"roles": {"backend": null}}'])
def test_damaged_config_is_reported_and_never_overwritten(project, contents):
    config = project / ".task-management" / "config.json"
    config.write_text(contents, encoding="utf-8")
    for command in (["config", "show"], ["team", "show"], ["validate"], ["init"],
                    ["config", "set", "parallel.max_parallel=3"]):
        refused(cli(project, *command), str(config), "无法使用")
        # A file read as "no configuration" used to be saved back as the defaults, dropping its roles.
        assert config.read_text(encoding="utf-8") == contents


def test_limit_that_is_not_a_number_names_the_setting_and_the_fix(tmp_path):
    config = ExecutionConfig(tmp_path)
    config.config["parallel"]["max_parallel"] = "many"
    with pytest.raises(ConfigError, match="config set parallel.max_parallel"):
        config.get_max_parallel()


def test_damaged_checkpoint_is_reported_and_kept_aside_when_rebuilt(project):
    checkpoint = project / ".task-management" / "checkpoint.json"
    checkpoint.write_text('{"data": {"spec_file": "planning/specs/keep.md"', encoding="utf-8")
    damaged = checkpoint.read_text(encoding="utf-8")
    refused(cli(project, "checkpoint", "check"), str(checkpoint), "foreman execution sync")
    assert checkpoint.read_text(encoding="utf-8") == damaged
    # begin ends by syncing the checkpoint; the step itself must still go through.
    started = cli(project, "execution", "begin", "001")
    assert started.returncode == 0 and json.loads(started.stdout)["task_id"] == "001", started.stderr
    assert "checkpoint.json.corrupted" in started.stderr
    assert checkpoint.with_name("checkpoint.json.corrupted").read_text(encoding="utf-8") == damaged
    assert "active_tasks: ['001']" in cli(project, "checkpoint", "check").stdout


@pytest.mark.parametrize("contents", ['{"tasks": [', "[]", '{"tasks": {"a": 1}}', '{"tasks": [{"title": "x"}, "text"]}'])
def test_damaged_task_board_is_reported_and_left_alone(project, contents):
    board = project / "planning" / "tasks.json"
    board.write_text(contents, encoding="utf-8")
    for command in (["show"], ["status"], ["add", "--file", "plan.json", "--replace"]):
        refused(cli(project, *command), str(board), "文件没有被改动")
    assert board.read_text(encoding="utf-8") == contents


def test_number_as_task_id_in_a_hand_edited_board_is_shown_and_flagged(project):
    (project / "planning" / "tasks.json").write_text('{"tasks": [{"id": 7, "title": "数字编号"}]}', encoding="utf-8")
    shown = cli(project, "show", "7")
    assert shown.returncode == 0 and "数字编号" in shown.stdout, shown.stderr
    checked = cli(project, "validate")
    assert checked.returncode == 1 and "缺少字符串形式的任务编号" in checked.stdout
    refused(cli(project, "execution", "begin", "7"))


def test_damaged_execution_record_is_named_and_does_not_hide_the_others(project):
    first = json.loads(cli(project, "execution", "begin", "001").stdout)["execution_id"]
    assert cli(project, "execution", "finish", "001", "--outcome", "failed").returncode == 0
    assert cli(project, "execution", "retry", "001", "--reason", "只写了一半").returncode == 0
    second = json.loads(cli(project, "execution", "begin", "001").stdout)["execution_id"]
    record = project / ".task-management" / "history" / f"{second}.json"
    record.write_text("{", encoding="utf-8")

    listed = cli(project, "history")
    assert listed.returncode == 0 and first[:3] in listed.stdout and record.name in listed.stderr
    recovered = cli(project, "execution", "recover")
    assert [item["execution_id"] for item in json.loads(recovered.stdout)["records"]] == [first]
    assert record.name in recovered.stderr
    refused(cli(project, "execution", "inspect", "001"), str(record), "无法使用")
    shown = cli(project, "show", "001")
    # The board still points at a record: this is not a task from before records existed.
    refused(shown, str(record))
    assert "旧任务" not in shown.stdout
    assert record.read_text(encoding="utf-8") == "{"


def test_missing_execution_record_is_not_mistaken_for_a_legacy_task(project):
    execution_id = json.loads(cli(project, "execution", "begin", "001").stdout)["execution_id"]
    (project / ".task-management" / "history" / f"{execution_id}.json").unlink()
    shown = cli(project, "show", "001")
    assert shown.returncode == 0 and "旧任务" not in shown.stdout
    assert f"恢复 .task-management/history/{execution_id}.json" in shown.stdout
    refused(cli(project, "execution", "inspect", "001"), f"找不到受管执行记录 {execution_id}")


@pytest.mark.parametrize("command", [
    ["show", "999"], ["update", "999", "PENDING"], ["fail", "999"], ["plan-execution", "999"],
    ["acceptance", "999"], ["acceptance", "999", "--template"], ["execution", "begin", "999"],
    # Looked up before the dispatcher model, so a typo is not reported as a settings problem.
    ["run", "999", "--dispatcher", "custom:none"],
])
def test_unknown_task_is_named(project, command):
    refused(cli(project, *command), "任务 999 不存在")


def test_input_files_that_cannot_be_used_are_named(project):
    refused(cli(project, "add", "--file", "missing.json"), "找不到任务文件 missing.json", str(project))
    (project / "bad.json").write_text("{\n", encoding="utf-8")
    refused(cli(project, "add", "--file", "bad.json"), "任务文件 bad.json 不是合法的 JSON", "第 2 行")
    piped = subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), "add", "--file", "-"], cwd=project,
                           capture_output=True, text=True, input="{")
    refused(piped, "标准输入 不是合法的 JSON")
    refused(cli(project, "team", "set", "backend", "--model", "custom:none", "--description", "接口",
                "--instructions-file", "missing.md"), "找不到系统提示文件 missing.md")

    assert cli(project, "execution", "begin", "001").returncode == 0
    assert cli(project, "execution", "finish", "001", "--outcome", "completed").returncode == 0
    refused(cli(project, "execution", "accept", "001", "--evidence-file", "missing.json"),
            "找不到验收证据文件 missing.json")
    refused(cli(project, "execution", "accept", "001", "--evidence-file", "bad.json"), "验收证据文件 bad.json")
    (project / "list.json").write_text("[]", encoding="utf-8")
    refused(cli(project, "execution", "accept", "001", "--evidence-file", "list.json"),
            "JSON 对象", "foreman acceptance <任务ID> --template")
    (project / "failed.json").write_text(json.dumps({
        "inspection": "看过", "checks": [{"id": "copy", "status": "failed", "evidence": ""}],
    }), encoding="utf-8")
    refused(cli(project, "execution", "accept", "001", "--evidence-file", "failed.json"), "缺少证据: copy")
    (project / "partial.json").write_text('{"inspection": "看过", "checks": []}', encoding="utf-8")
    refused(cli(project, "execution", "accept", "001", "--evidence-file", "partial.json"), "应有的 id: copy")


def test_argument_values_are_checked_before_anything_is_written(project):
    config = project / ".task-management" / "config.json"
    before = config.read_text(encoding="utf-8")
    refused(cli(project, "update", "001", "pending"), "状态 pending 无效", "是不是 PENDING")
    refused(cli(project, "update", "001", "BOGUS"), "状态 BOGUS 无效", "IN_PROGRESS")
    assert TaskBoard.load(project).get_task("001")["status"] == "PENDING"
    refused(cli(project, "config", "set", "parallel.max_parallel=abc"), "parallel.max_parallel 要是整数")
    refused(cli(project, "config", "set", "parallel.max_parallel=0"), "不能小于 1")
    refused(cli(project, "config", "set", "execution.bogus=worker"), "不支持的配置键: execution.bogus")
    refused(cli(project, "config", "set", "unknown.key=1"), "parallel.max_retries", "foreman team set")
    refused(cli(project, "config", "set", "foo"), "key=value")
    assert config.read_text(encoding="utf-8") == before
    assert cli(project, "config", "set", "parallel.max_retries=0").returncode == 0

    refused(cli(project, "checkpoint", "save"), "--phase")
    refused(cli(project, "checkpoint", "save", "--phase", "developing", "--data", "foo"), "key=value", "'foo'")
    # A data key named like the parameter used to end in a traceback.
    saved = cli(project, "checkpoint", "save", "--phase", "developing", "--data", "phase=x", "self=y")
    assert saved.returncode == 0, saved.stderr
    assert "phase: x" in cli(project, "checkpoint", "check").stdout


def test_dispatch_prerequisites_are_explained(project):
    settings = project.parent / "home" / ".factory" / "settings.json"
    # A task without a role needs neither models nor droid, so that is what it is told.
    refused(cli(project, "run", "001", "--dispatcher", "custom:fake"), "当前会话直接执行")
    for command in (["models"], ["run", "002", "--dispatcher", "custom:fake"],
                    ["preflight", "--dispatcher", "custom:fake"],
                    ["team", "set", "backend", "--model", "custom:fake", "--description", "接口"]):
        refused(cli(project, *command), f"找不到模型配置 {settings}", "customModels")
    checked = cli(project, "team", "check")
    assert checked.returncode == 0 and "还没有配置角色" in checked.stdout, checked.stderr

    settings.parent.mkdir()
    settings.write_text("{\n", encoding="utf-8")
    refused(cli(project, "models"), f"模型配置 {settings} 不是合法的 JSON", "第 2 行")
    settings.write_text(json.dumps({"customModels": [
        {"model": "fake", "id": "custom:fake", "baseUrl": "http://127.0.0.1:9"},
    ]}), encoding="utf-8")
    refused(cli(project, "run", "002", "--dispatcher", "custom:other"), "调度模型 custom:other", "foreman models")
    refused(cli(project, "preflight", "--dispatcher", "custom:other"), "探针模型 custom:other", "foreman models")
    for command in (["preflight", "--dispatcher", "custom:fake"], ["run", "002", "--dispatcher", "custom:fake"]):
        refused(cli(project, *command), "找不到 droid 命令", "PATH")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


def test_commit_that_cannot_be_resolved_says_what_is_wrong_with_the_repository(project):
    for command in (["integrate", "001", "--commit", "HEAD"], ["delivery", "--commit", "HEAD", "--paths", "a.txt"]):
        refused(cli(project, *command), f"{project.resolve()} 不是 git 仓库")
    git(project, "init", "-q")
    refused(cli(project, "integrate", "001", "--commit", "HEAD"), "还没有任何提交")
    git(project, "add", "plan.json")
    git(project, "commit", "-qm", "test: record a commit to look up")
    refused(cli(project, "integrate", "001", "--commit", "nosuchref"), "找不到提交 nosuchref")


def test_begin_says_why_a_task_cannot_start(project):
    board = TaskBoard.load(project)
    board.add_tasks([task("003", dependencies=["001"]), task("004"), task("005")])
    workflow = Workflow(project)
    with pytest.raises(ValueError, match="任务尚不可开始：依赖未完成: #001"):
        workflow.begin("003")
    board.update_task_status("004", "pending")
    with pytest.raises(ValueError, match="状态是 pending"):
        workflow.begin("004")
    workflow.begin("001")
    with pytest.raises(ValueError, match="任务 001 已经登记开始.*foreman show 001"):
        workflow.begin("001")
    config = ExecutionConfig(project)
    config.config["parallel"]["max_parallel"] = 1
    config.save()
    with pytest.raises(ValueError, match="并发上限 1：任务 001 正在进行"):
        workflow.begin("005")
    workflow.finish(board.get_task("001")["execution_id"], "completed")
    with pytest.raises(ValueError, match="上次执行还没有了结.*foreman show 001"):
        workflow.begin("001")
    with pytest.raises(ValueError, match="现在是 AWAITING_REVIEW"):
        workflow.integration_ready("001")
