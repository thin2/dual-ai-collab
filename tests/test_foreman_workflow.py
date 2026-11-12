"""Regression tests for partial writes, exact model choice and managed dispatch."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

SKILL = Path(__file__).resolve().parents[1] / "foreman"
sys.path.insert(0, str(SKILL))

from lib.board import TaskBoard  # noqa: E402
from lib.checkpoint import CheckpointManager  # noqa: E402
from lib.config import ExecutionConfig  # noqa: E402
from lib.history import ExecutionHistory  # noqa: E402
from lib.plan import check_plan  # noqa: E402
from lib.probe import verify_receipt  # noqa: E402
from lib.runner import dispatch_events, run_task  # noqa: E402
from lib.safety import minimal_environment, runtime_policy  # noqa: E402
from lib.team import model_catalog  # noqa: E402
from lib.workflow import Workflow, delivery_check, snapshot  # noqa: E402


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    config = ExecutionConfig(root)
    config.set_role("frontend", {"droid": "tm-frontend", "model": "custom:proxy/claude",
                                 "description": "页面"})
    board = TaskBoard.load(root)
    board.save_document({"tasks": [{
        "id": "001", "title": "页面", "status": "PENDING", "role": "frontend",
        "files": ["page.txt"], "runtime_dependencies": ["page.txt"],
        "acceptance": [{"id": "copy", "scenario": "打开页面", "expected": "显示中文",
                        "method": "manual"}],
    }]})
    return root


def audited(workflow, execution_id, tmp_path, actual="custom:proxy/claude"):
    sessions = tmp_path / "sessions"
    folder = sessions / str(workflow.root).replace("/", "-")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "worker.jsonl").write_text(json.dumps({
        "id": "worker", "callingSessionId": "parent",
        "title": f"Tm-frontend: [tm:{execution_id}] 页面",
    }) + "\n", encoding="utf-8")
    (folder / "worker.settings.json").write_text(json.dumps({"model": actual}), encoding="utf-8")
    return workflow.audit(execution_id, sessions)


def evidence():
    return {"inspection": "检查了新增文件，原有用户文件未覆盖",
            "checks": [{"id": "copy", "status": "passed", "evidence": "实际打开页面观察到中文"}]}


def test_permission_failure_with_persisted_files_can_be_accepted(project, tmp_path):
    workflow = Workflow(project)
    checkpoint = CheckpointManager(project)
    checkpoint.save("developing", spec_file="planning/specs/keep.md")
    plan = workflow.begin("001")
    execution_id = plan["execution_id"]
    (project / "page.txt").write_text("中文", encoding="utf-8")
    workflow.finish(execution_id, "permission_rejected")
    assert workflow.inspect(execution_id)["added"] == ["page.txt"]
    assert workflow.board.get_task("001")["status"] == "AWAITING_REVIEW"
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())
    record = workflow.history._load_record(execution_id)
    assert record.status == "failed"
    assert record.details["dispatch_outcome"] == "permission_rejected"
    assert record.details["acceptance"]["status"] == "passed"
    assert workflow.board.get_task("001")["status"] == "AWAITING_INTEGRATION"
    assert checkpoint.load()["data"]["spec_file"] == "planning/specs/keep.md"


def test_interrupted_run_does_not_fabricate_end_time(project):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "interrupted")
    record = workflow.history._load_record(execution_id)
    assert record.end_time is None and record.duration_seconds is None
    assert record.recorded_at
    workflow.finish(execution_id, "interrupted")  # Idempotent.
    with pytest.raises(ValueError):
        workflow.finish(execution_id, "returned")


def test_retry_preserves_partial_work_and_records_reason(project):
    workflow = Workflow(project)
    (project / "page.txt").write_text("user baseline")
    first = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("partial")
    workflow.finish(first, "failed")
    workflow.retry(first, "已有部分页面；保留内容，只补错误提示")
    second = workflow.begin("001")
    assert first != second["execution_id"]
    assert "只补错误提示" in second["context"]
    assert (project / "page.txt").read_text() == "partial"
    with pytest.raises(ValueError, match="后续派发"):
        workflow.retry(first, "stale")


def test_running_task_cannot_be_retried_or_accepted(project):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    with pytest.raises(ValueError):
        workflow.retry(execution_id, "not finished")
    with pytest.raises(ValueError):
        workflow.accept(execution_id, evidence())
    with pytest.raises(ValueError):
        workflow.begin("001")


@pytest.mark.parametrize("actual", ["custom:wrong-route/claude", None])
def test_wrong_model_blocks_acceptance(project, tmp_path, actual):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "returned")
    assert audited(workflow, execution_id, tmp_path, actual)["status"] == "unverified"
    with pytest.raises(ValueError, match="模型"):
        workflow.accept(execution_id, evidence())


def test_prior_audit_cannot_satisfy_current_attempt(project, tmp_path):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    folder = tmp_path / "sessions" / str(workflow.root).replace("/", "-")
    path = folder / "worker.jsonl"
    path.write_text(path.read_text().replace(execution_id, "previous-attempt"))
    assert workflow.audit(execution_id, tmp_path / "sessions")["status"] == "unverified"


def test_empty_audit_is_unverified(project, tmp_path):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "returned")
    assert workflow.audit(execution_id, tmp_path / "empty")["status"] == "unverified"
    with pytest.raises(ValueError):
        workflow.accept(execution_id, evidence())


@pytest.mark.parametrize("bad", [
    {"inspection": "reviewed", "checks": []},
    {"checks": [{"id": "copy", "status": "passed", "evidence": "observed"}]},
    {"inspection": "reviewed", "checks": [{"id": "copy", "status": "failed", "evidence": "English"}]},
    {"inspection": "reviewed", "checks": [{"id": "copy", "status": "passed", "evidence": ""}]},
])
def test_acceptance_requires_every_observed_result(project, tmp_path, bad):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    with pytest.raises(ValueError):
        workflow.accept(execution_id, bad)


def test_edit_after_acceptance_invalidates_integration(project, tmp_path):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("accepted")
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())
    workflow.integration_ready("001")
    (project / "page.txt").write_text("changed")
    with pytest.raises(ValueError, match="文件已变化"):
        workflow.integration_ready("001")


def test_retry_invalidates_prior_acceptance(project, tmp_path):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())
    workflow.retry(execution_id, "审查发现遗漏，需要新一轮")
    with pytest.raises(ValueError):
        workflow.integration_ready("001")
    with pytest.raises(ValueError):
        workflow.accept(execution_id, evidence())


def test_begin_requires_structured_acceptance(project):
    board = TaskBoard.load(project)
    document = board.get_document()
    document["tasks"][0].pop("acceptance")
    board.save_document(document)
    with pytest.raises(ValueError, match="acceptance"):
        Workflow(project).begin("001")
    assert not ExecutionHistory(project).get_all_history()


def test_concurrent_disjoint_tasks_preserve_board_and_checkpoint(project):
    board = TaskBoard.load(project)
    document = board.get_document()
    document["tasks"].append({**document["tasks"][0], "id": "002", "files": ["other.txt"]})
    board.save_document(document)
    with ThreadPoolExecutor(max_workers=2) as pool:
        plans = list(pool.map(lambda tid: Workflow(project).begin(tid), ["001", "002"]))
    assert len({p["execution_id"] for p in plans}) == 2
    assert all(t["status"] == "IN_PROGRESS" for t in board.get_all_tasks())
    assert set(CheckpointManager(project).load()["data"]["active_tasks"]) == {"001", "002"}


@pytest.mark.parametrize("path", ["../outside", "/tmp/absolute", ".env", ".factory/droids/x", "**/*.py"])
def test_snapshot_rejects_unsafe_or_unbounded_scope(project, path):
    with pytest.raises(ValueError):
        snapshot(project, [path])


def test_snapshot_rejects_symlink_without_reading_target(project, tmp_path):
    target = tmp_path / "dummy"
    target.write_text("not a real secret")
    (project / "page.txt").symlink_to(target)
    with pytest.raises(ValueError, match="符号链接"):
        snapshot(project, ["page.txt"])


def test_history_ids_unique_and_legacy_record_loads(project):
    history = ExecutionHistory(project)
    ids = {history.record_start("001", "worker", "medium") for _ in range(20)}
    assert len(ids) == 20
    legacy = asdict(history._load_record(next(iter(ids))))
    for field in ("details", "execution_id", "recorded_at"):
        legacy.pop(field)
    (history.history_dir / "001-legacy.json").write_text(json.dumps(legacy))
    assert len(history.get_task_history("001")) == 21
    with pytest.raises(ValueError):
        history._load_record("../escape")


def test_catalog_preserves_same_names_and_nonrecommended_routes(tmp_path):
    settings = tmp_path / "fixture.json"
    settings.write_text(json.dumps({"customModels": [
        {"id": "custom:direct/claude", "model": "claude", "displayName": "Claude", "apiKey": "fake"},
        {"id": "custom:proxy/route/claude", "model": "claude", "displayName": "Claude", "apiKey": "fake"},
        {"id": "custom:other/model", "model": "another", "apiKey": "fake"},
    ]}))
    catalog = model_catalog(settings, recommended=["custom:proxy/route/claude"])
    assert catalog["total"] == catalog["matches"] == 3
    assert catalog["models"][0]["id"] == "custom:proxy/route/claude"
    assert catalog["models"][1]["id"] == "custom:direct/claude"
    assert "apiKey" not in json.dumps(catalog)
    filtered = model_catalog(settings, query="direct")
    assert filtered["total"] == 3 and filtered["matches"] == 1
    assert model_catalog(settings, query="missing")["matches"] == 0


def test_environment_drops_ambient_keys(monkeypatch):
    monkeypatch.setenv("PROVIDER_API_KEY", "fake")
    monkeypatch.setenv("FACTORY_API_KEY", "fake")
    assert "PROVIDER_API_KEY" not in minimal_environment()
    assert "FACTORY_API_KEY" not in minimal_environment()
    assert minimal_environment()["HOME"] == str(Path.home())


def test_dispatcher_normal_exit_does_not_hide_task_error():
    events = "\n".join(json.dumps(event) for event in [
        {"type": "tool_result", "isError": True, "result": "daemon unavailable"},
        {"type": "completion", "is_error": False},
    ])
    outcome, diagnostic = dispatch_events(events, 0)
    assert outcome == "failed"
    assert diagnostic["tool_errors"] == 1
    assert dispatch_events("plain unsupported output", 0)[0] == "failed"
    assert dispatch_events('{"type":"completion","reason":"permission_rejected"}', 1)[0] == "permission_rejected"


def test_changed_task_status_does_not_bypass_recovery(project):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "failed")
    workflow.board.update_task_status("001", "PENDING")
    with pytest.raises(ValueError, match="明确 retry"):
        workflow.begin("001")


def test_native_policy_blocks_project_secrets_and_metadata(project):
    (project / ".env.local").write_text("fake")
    policy = runtime_policy(project)
    assert str(project / ".env.local") in policy["sandbox"]["filesystem"]["denyRead"]
    assert str(project / ".factory") in policy["sandbox"]["filesystem"]["denyWrite"]
    assert policy["cloudSessionSync"] is False
    assert policy["sandbox"]["enabled"]
    assert not (project / ".factory/settings.json").exists()
    with pytest.raises(ValueError, match="preflight"):
        verify_receipt(project, "custom:dispatcher", "droid")


def test_guard_checks_paths_not_document_body(project):
    spec = importlib.util.spec_from_file_location("guard", SKILL / "tools" / "dispatch_guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    policy = {"root": str(project), "task_args": {"subagent_type": "tm-frontend"},
              "write_scopes": [str(project / "page.txt")]}
    patch_text = f"*** Update File: {project}/page.txt\n+Documentation mentions settings.json and .env\n"
    assert guard.validate({"tool_name": "ApplyPatch", "tool_input": {"input": patch_text}}, policy) is None
    assert guard.validate({"tool_name": "Read", "tool_input": {"file_path": str(project / ".env")}}, policy)
    assert guard.validate({"tool_name": "Execute", "tool_input": {"command": "pwd", "cwd": str(project)}}, policy)
    assert guard.validate({"tool_name": "Task", "tool_input": {"subagent_type": "other"}}, policy)
    assert guard.validate({"tool_name": "Script", "tool_input": {}}, policy) is None


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)


def test_delivery_catches_uncommitted_runtime_dependency_and_deletion(project):
    git(project, "init", "-q")
    (project / "page.txt").write_text("committed")
    git(project, "add", "page.txt")
    git(project, "commit", "-qm", "test: record delivery fixture")
    assert delivery_check(project, "HEAD", ["page.txt"])["ok"]
    (project / "runtime.py").write_text("uncommitted")
    report = delivery_check(project, "HEAD", ["page.txt", "runtime.py"])
    assert {"path": "runtime.py", "reason": "missing_from_commit"} in report["issues"]
    (project / "page.txt").unlink()
    assert not delivery_check(project, "HEAD", ["page.txt"])["ok"]


def test_runner_records_process_failure_after_partial_write(project, tmp_path):
    class FakeProcess:
        pid = 123
        returncode = 1

        def communicate(self, timeout=None):
            (project / "page.txt").write_text("partial")
            return '{"subtype":"permission_rejected"}', ""

        def poll(self):
            return self.returncode

    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_capabilities"), patch("lib.runner.verify_receipt"), \
         patch("lib.workflow.worktree_state", return_value=None), \
         patch("lib.runner.check_team", return_value=[{"role": "frontend", "ok": True}]), \
         patch("lib.runner.subprocess.Popen", return_value=FakeProcess()), \
         patch("lib.workflow.audit_runs", return_value=[]):
        result = run_task(project, "001", "custom:dispatcher")
    assert result["dispatch_outcome"] == "permission_rejected"
    assert result["inspection"]["added"] == ["page.txt"]
    assert result["audit"]["status"] == "unverified"
    assert TaskBoard.load(project).get_task("001")["status"] == "AWAITING_REVIEW"


def test_cli_recovery_and_failure_reason(project):
    def cli(*args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=project, capture_output=True, text=True)
    started = cli("execution", "begin", "001")
    assert started.returncode == 0, started.stderr
    execution_id = json.loads(started.stdout)["execution_id"]
    assert cli("fail", "001", "--reason", "do not restart blindly").returncode == 1
    assert cli("execution", "finish", execution_id, "--outcome", "interrupted").returncode == 0
    recovered = json.loads(cli("execution", "recover").stdout)
    assert recovered["records"][0]["duration_seconds"] is None
    assert cli("execution", "retry", execution_id, "--reason", "保留部分文件并补验证").returncode == 0
    assert TaskBoard.load(project).get_task("001")["last_failure"] == "保留部分文件并补验证"


def test_managed_process_through_acceptance_and_clean_checkout(project, tmp_path):
    """Use a deterministic fake transport, but real processes, files, Git and CLI."""
    fake = tmp_path / "fake-droid"
    sessions = tmp_path / "fake-sessions"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys,pathlib,re,subprocess\n"
        "if '--help' in sys.argv:\n"
        " print('--settings --only-tools --output-format --model --auto'); sys.exit(0)\n"
        "args=json.loads(sys.argv[-1].split('\\n',1)[1])\n"
        "execution_id=re.search(r'\\[tm:([^]]+)\\]',args['description']).group(1)\n"
        "if 'Create' not in sys.argv[sys.argv.index('--only-tools')+1].split(','): sys.exit(3)\n"
        "settings=json.loads(pathlib.Path(sys.argv[sys.argv.index('--settings')+1]).read_text())\n"
        "hook=settings['hooks']['PreToolUse'][0]['hooks'][0]['command']\n"
        "event=json.dumps({'session_id':'parent','tool_name':'Task','tool_input':args})\n"
        "if subprocess.run(hook,shell=True,input=event,text=True).returncode: sys.exit(4)\n"
        "print(json.dumps({'type':'system','subtype':'init','session_id':'parent'}))\n"
        "root=pathlib.Path.cwd()\n"
        "(root/'page.txt').write_text('中文\\n')\n"
        f"folder=pathlib.Path({str(sessions)!r})/str(root.resolve()).replace('/','-')\n"
        "folder.mkdir(parents=True)\n"
        "(folder/'child.jsonl').write_text(json.dumps({'id':'child','callingSessionId':'parent',"
        "'title':'Tm-frontend: '+args['description']})+'\\n')\n"
        "(folder/'child.settings.json').write_text(json.dumps({'model':'custom:proxy/claude'}))\n"
        "print(json.dumps({'type':'completion','is_error':False}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o700)
    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_team", return_value=[{"role": "frontend", "ok": True}]), \
         patch("lib.runner.verify_receipt"), patch("lib.team.DEFAULT_SESSIONS", sessions):
        result = run_task(project, "001", "custom:dispatcher", executable=str(fake))
    assert result["dispatch_outcome"] == "returned"
    assert result["audit"]["status"] == "passed"
    assert (project / "page.txt").read_text() == "中文\n"
    workflow = Workflow(project)
    workflow.accept(result["execution_id"], evidence())
    git(project, "init", "-q")
    git(project, "add", "page.txt")
    git(project, "commit", "-qm", "test: record accepted workflow fixture")
    commit = git(project, "rev-parse", "HEAD").stdout.strip()
    workflow.integration_ready("001", commit, project)
    integrated = subprocess.run(
        [sys.executable, str(SKILL / "tools/cli.py"), "integrate", "001", "--commit", commit],
        cwd=project, text=True, capture_output=True,
    )
    assert integrated.returncode == 0, integrated.stderr
    assert workflow.board.get_task("001")["status"] == "DONE"
    with pytest.raises(ValueError):
        workflow.accept(result["execution_id"], evidence())
    assert CheckpointManager(project).load()["data"]["completed_tasks"] == 1
    checkout = tmp_path / "clean-checkout"
    git(project, "clone", "--quiet", "--no-hardlinks", str(project), str(checkout))
    assert (checkout / "page.txt").read_text() == "中文\n"
    assert not (checkout / ".task-management").exists()


def test_runner_timeout_kills_owned_process_and_records_end(project):
    class HungProcess:
        pid = 12345
        returncode = None

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("fake", timeout)
            self.returncode = -9
            return "", ""

        def poll(self):
            return self.returncode

    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_capabilities"), patch("lib.runner.verify_receipt"), \
         patch("lib.workflow.worktree_state", return_value=None), \
         patch("lib.runner.check_team", return_value=[{"role": "frontend", "ok": True}]), \
         patch("lib.runner.subprocess.Popen", return_value=HungProcess()), \
         patch("lib.runner.os.killpg") as kill, patch("lib.workflow.audit_runs", return_value=[]):
        result = run_task(project, "001", "custom:dispatcher", timeout=1)
    kill.assert_called_once()
    record = ExecutionHistory(project)._load_record(result["execution_id"])
    assert record.details["dispatch_outcome"] == "interrupted"
    assert record.end_time and record.duration_seconds is not None


def test_installed_profile_contains_managed_entrypoints(tmp_path):
    target = tmp_path / "installed"
    installer = SKILL.parent / "install.py"
    result = subprocess.run(
        [sys.executable, str(installer), "--profile", "foreman",
         "--source", str(SKILL.parent), "--target", str(target)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "tools/dispatch_guard.py").exists()
    assert (target / "references/managed-workflow.md").exists()
    cli = subprocess.run([sys.executable, str(target / "tools/cli.py"), "--help"],
                         cwd=tmp_path, capture_output=True, text=True)
    assert cli.returncode == 0, cli.stderr
    assert all(command in cli.stdout for command in ("preflight", "execution", "delivery"))
    # bin/foreman is the same program under the name its own output tells people to type.
    launcher = subprocess.run([str(target / "bin/foreman"), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert launcher.returncode == 0, launcher.stderr
    assert launcher.stdout == cli.stdout and cli.stdout.startswith("usage: foreman ")


def accepted_run(workflow, tmp_path):
    execution_id = workflow.begin("001")["execution_id"]
    (workflow.root / "page.txt").write_text("accepted")
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())
    return execution_id


def set_task(project, **fields):
    board = TaskBoard.load(project)
    document = board.get_document()
    document["tasks"][0].update(fields)
    board.save_document(document)


def load_guard():
    spec = importlib.util.spec_from_file_location("guard", SKILL / "tools" / "dispatch_guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def test_runtime_dependency_change_after_acceptance_blocks_integration(project, tmp_path):
    (project / "runtime.py").write_text("print('accepted')")
    set_task(project, runtime_dependencies=["page.txt", "runtime.py"])
    workflow = Workflow(project)
    accepted_run(workflow, tmp_path)
    workflow.integration_ready("001")
    (project / "runtime.py").write_text("raise SystemExit")
    with pytest.raises(ValueError, match="运行依赖已变化.*runtime.py"):
        workflow.integration_ready("001")
    (project / "runtime.py").write_text("print('accepted')")
    workflow.integration_ready("001")
    set_task(project, runtime_dependencies=["page.txt"])
    with pytest.raises(ValueError, match="运行依赖声明"):
        Workflow(project).integration_ready("001")


def test_begin_requires_runtime_dependencies(project):
    set_task(project, runtime_dependencies=[])
    with pytest.raises(ValueError, match="runtime_dependencies"):
        Workflow(project).begin("001")
    assert not ExecutionHistory(project).get_all_history()


@pytest.mark.parametrize("lost", ["board", "checkpoint"])
def test_repeating_finish_repairs_interrupted_bookkeeping(project, tmp_path, lost):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    target = (workflow.board, "update_task_status") if lost == "board" else (workflow, "sync")
    with patch.object(*target, side_effect=OSError("interrupted")), pytest.raises(OSError):
        workflow.finish(execution_id, "returned")
    record = workflow.history._load_record(execution_id)
    assert (record.status, record.details["dispatch_outcome"]) == ("success", "returned")
    resumed = Workflow(project)
    with pytest.raises(ValueError, match="已登记"):
        resumed.finish(execution_id, "failed")
    resumed.finish(execution_id, "returned")
    assert resumed.board.get_task("001")["status"] == "AWAITING_REVIEW"
    assert CheckpointManager(project).load()["data"]["active_tasks"] == []
    audited(resumed, execution_id, tmp_path)
    resumed.accept(execution_id, evidence())
    assert resumed.board.get_task("001")["status"] == "AWAITING_INTEGRATION"


def test_repeating_finish_does_not_reopen_reviewed_task(project, tmp_path):
    workflow = Workflow(project)
    execution_id = accepted_run(workflow, tmp_path)
    workflow.finish(execution_id, "returned")
    assert workflow.board.get_task("001")["status"] == "AWAITING_INTEGRATION"


def test_blocked_task_resumes_only_through_unblock(project):
    config = ExecutionConfig(project)
    config.config["parallel"]["max_retries"] = 0
    config.save()
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    workflow.finish(execution_id, "failed")
    with pytest.raises(ValueError, match="BLOCKED"):
        workflow.unblock(execution_id, "not blocked yet")
    workflow.retry(execution_id, "模型端点不可用")
    assert workflow.board.get_task("001")["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="unblock"):
        workflow.retry(execution_id, "again")
    assert workflow.board.get_task("001")["failed_attempts"] == 1

    def cli(*args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=project, capture_output=True, text=True)
    refused = cli("update", "001", "PENDING", "--reset-retries")
    assert refused.returncode == 1 and "unblock" in refused.stderr
    with pytest.raises(ValueError):
        workflow.begin("001")
    unblocked = cli("execution", "unblock", execution_id, "--reason", "用户已恢复端点")
    assert unblocked.returncode == 0, unblocked.stderr
    task = workflow.board.get_task("001")
    assert (task["status"], task["failed_attempts"]) == ("PENDING", 0)
    assert "模型端点不可用" in task["last_failure"] and "用户已恢复端点" in task["last_failure"]
    record = workflow.history._load_record(execution_id)
    assert record.details["recovery"]["unblocked"] and len(record.details["recovery_history"]) == 1
    assert workflow.begin("001")["execution_id"] != execution_id


def test_env_templates_are_deliverable_while_secrets_stay_protected(project):
    (project / ".env.example").write_text("KEY=")
    (project / ".env.local").write_text("fake")
    assert list(snapshot(project, [".env.example"])) == [".env.example"]
    with pytest.raises(ValueError):
        snapshot(project, [".env.local"])
    denied = runtime_policy(project)["sandbox"]["filesystem"]["denyRead"]
    assert str(project / ".env.local") in denied and str(project / ".env.example") not in denied
    guard = load_guard()
    policy = {"root": str(project), "task_args": {}, "write_scopes": []}

    def read(name):
        return guard.validate({"tool_name": "Read", "tool_input": {"file_path": str(project / name)}}, policy)
    assert read(".env.example") is None
    assert read(".env.local")


def test_board_updates_from_separate_processes_are_not_lost(project):
    board = TaskBoard.load(project)
    document = board.get_document()
    document["tasks"].append({**document["tasks"][0], "id": "002", "files": ["other.txt"]})
    board.save_document(document)
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; from lib.board import TaskBoard\n"
            "board = TaskBoard.load(Path(sys.argv[2]))\n"
            "for _ in range(100): board.record_failure(sys.argv[3], 10**9)\n")
    processes = [subprocess.Popen([sys.executable, "-c", code, str(SKILL), str(project), task_id])
                 for task_id in ("001", "002")]
    assert [process.wait(timeout=60) for process in processes] == [0, 0]
    assert [board.get_task(task_id)["failed_attempts"] for task_id in ("001", "002")] == [100, 100]


def test_integrate_can_be_repeated_after_lost_board_update(project, tmp_path):
    workflow = Workflow(project)
    execution_id = accepted_run(workflow, tmp_path)
    git(project, "init", "-q")
    git(project, "add", "page.txt")
    git(project, "commit", "-qm", "test: record accepted page")
    commit = git(project, "rev-parse", "HEAD").stdout.strip()
    with patch.object(workflow.board, "confirm_integration", side_effect=OSError("interrupted")), \
         pytest.raises(OSError):
        workflow.integrate("001", commit, project)
    assert workflow.board.get_task("001")["status"] == "AWAITING_INTEGRATION"
    task = Workflow(project).integrate("001", commit, project, "ok")
    assert task["status"] == "DONE" and task["integration"]["commit"] == commit
    assert workflow.history._load_record(execution_id).details["integration"]["commit"] == commit
    recorded = task["integration"]["timestamp"]
    with patch.object(workflow, "sync") as sync:
        assert workflow.integrate("001", commit, project)["integration"]["timestamp"] == recorded
    sync.assert_called_once()
    with pytest.raises(ValueError, match="已集成"):
        workflow.integrate("001", "0" * 40, project)


def test_guard_limits_dispatcher_to_one_task_and_keeps_worker_in_scope(project, tmp_path):
    guard = load_guard()
    task_args = {"subagent_type": "tm-frontend", "prompt": "do"}
    policy = {"root": str(project), "task_args": task_args, "state": str(tmp_path / "dispatcher"),
              "write_scopes": [str(project / "page.txt")]}

    def call(session, tool, **tool_input):
        return guard.validate({"session_id": session, "tool_name": tool, "tool_input": tool_input}, policy)

    page = str(project / "page.txt")
    assert call("worker", "Read", file_path=page)  # Nothing may run before the dispatch.
    assert call(None, "Task", **task_args)
    assert call("dispatcher", "Task", **task_args) is None
    assert call("dispatcher", "Task", **task_args)  # No second dispatch.
    assert call("other", "Task", **task_args)
    assert call("dispatcher", "Execute", command="ls", riskLevel="low", summary="list")
    assert call("dispatcher", "Create", file_path=page, content="x")
    assert call("dispatcher", "Script", script="1") is None
    assert call("worker", "Execute", command="ls", riskLevel="low", summary="list") is None
    assert call("worker", "Create", file_path=page, content="x") is None
    assert call("worker", "Create", file_path=str(project / "other.txt"), content="x")


@pytest.mark.parametrize("read_only, tools", [
    (False, "Task,Read,LS,Grep,Glob,Create,Edit,ApplyPatch,Execute"),
    (True, "Task,Read,LS,Grep,Glob"),
])
def test_runner_lists_worker_tools_and_rejects_unverified_dispatcher(project, read_only, tools):
    ExecutionConfig(project).set_role("frontend", {"droid": "tm-frontend", "model": "custom:proxy/claude",
                                                   "description": "页面", "read_only": read_only})

    class Returned:
        pid = 123
        returncode = 0

        def communicate(self, timeout=None):
            events = ({"type": "system", "session_id": "dispatcher"}, {"type": "completion", "is_error": False})
            return "\n".join(json.dumps(event) for event in events), ""

        def poll(self):
            return self.returncode

    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_capabilities"), patch("lib.runner.verify_receipt"), \
         patch("lib.workflow.worktree_state", return_value=None), \
         patch("lib.runner.check_team", return_value=[{"role": "frontend", "ok": True}]), \
         patch("lib.runner.subprocess.Popen", return_value=Returned()) as popen, \
         patch("lib.workflow.audit_runs", return_value=[{"actual": "custom:proxy/claude"}]):
        result = run_task(project, "001", "custom:dispatcher")
    argv = popen.call_args[0][0]
    assert argv[argv.index("--only-tools") + 1] == tools
    # The hook never ran here, so nothing shows the dispatcher was held to one Task call.
    assert result["audit"]["status"] == "passed"
    assert result["dispatch_outcome"] == "failed"
    assert "guard_state_mismatch" in result["transport"]["error_categories"]


def plan_task(task_id="001", **fields):
    task = {"id": task_id, "title": "页面", "status": "PENDING", "role": "frontend",
            "description": "实现页面", "files": [f"page-{task_id}.txt"],
            "runtime_dependencies": [f"page-{task_id}.txt"],
            "acceptance": [{"id": "copy", "scenario": "打开页面", "expected": "显示中文",
                            "method": "manual"}]}
    task.update(fields)
    return task


def save_plan(project, *tasks):
    TaskBoard.load(project).save_document({"tasks": list(tasks)})


def test_plan_check_passes_a_dispatchable_board(project):
    save_plan(project, plan_task("001"), plan_task("002", dependencies=["001"]))
    assert check_plan(project) == {"ok": True, "checked": ["001", "002"], "direct": [], "board": [], "team": []}
    Workflow(project).begin("001")


@pytest.mark.parametrize(("field", "change"), [
    ("acceptance", {"acceptance": []}),
    ("acceptance", {"acceptance": [{"id": "a", "scenario": "s", "expected": "e", "method": "command"}]}),
    ("files", {"files": "page.txt"}),
    ("files", {"files": []}),
    ("files", {"files": ["../outside.txt"]}),
    ("runtime_dependencies", {"runtime_dependencies": None}),
    ("runtime_dependencies", {"runtime_dependencies": [".env"]}),
    ("role", {"role": 7}),
    ("dependencies", {"dependencies": "#009"}),
    ("status", {"status": "pending"}),
])
def test_plan_check_reports_what_begin_would_reject(project, field, change):
    save_plan(project, plan_task("001", **change))
    report = check_plan(project)
    assert report["ok"] is False and report["team"] == []
    assert [(item["task"], item["field"]) for item in report["board"]] == [("001", field)]
    with pytest.raises(ValueError):
        Workflow(project).begin("001")
    assert not ExecutionHistory(project).get_all_history()


def test_plan_check_reports_missing_description_and_unconfigured_role(project):
    save_plan(project, plan_task("001", description=""),
              plan_task("002", role="backend"), plan_task("003", role="backend"))
    report = check_plan(project)
    assert [(item["task"], item["field"]) for item in report["board"]] == [("001", "description")]
    assert [(item["role"], item["tasks"]) for item in report["team"]] == [("backend", ["002", "003"])]
    with pytest.raises(ValueError, match="未配置"):
        Workflow(project).begin("002")
    ExecutionConfig(project).set_role("backend", {"droid": "tm-backend", "model": "custom:proxy/gpt",
                                                  "description": "接口"})
    save_plan(project, plan_task("001", description="", sections=[{"heading": "任务描述", "body": "实现页面"}]),
              plan_task("002", role="backend"))
    assert check_plan(project)["ok"] is True


def test_mixed_priority_spellings_sort_instead_of_crashing(project):
    save_plan(project, plan_task("001", priority="P2"), plan_task("002", priority=2),
              plan_task("003", priority="3"), plan_task("004", priority="P1"),
              plan_task("005", priority="urgent"), plan_task("006", priority=None), plan_task("007"))
    assert check_plan(project)["ok"] is True
    board = TaskBoard.load(project)
    # Numbers first (larger wins, missing counts as 1), then P1 before P2, then anything unreadable.
    assert [task["id"] for task in board.get_open_tasks()] == ["003", "002", "007", "004", "001", "005", "006"]
    roles = {"frontend": {"model": "custom:proxy/claude"}}
    assert board.get_next_task(roles)["id"] == "003"
    assert [task["id"] for task in board.select_batch(roles, max_parallel=4)["batch"]] == ["003", "002", "007", "004"]


def test_plan_check_reports_cycles_duplicates_and_unintegrated_dependencies(project):
    save_plan(project,
              plan_task("001", dependencies="#003"),
              plan_task("002", dependencies="#001"),
              plan_task("003", dependencies="#002"),
              {"id": "004", "title": "旧任务", "status": "DONE"},
              plan_task("005", dependencies="#004"),
              plan_task("5"),
              plan_task("006", dependencies="#006"))
    report = check_plan(project)
    assert report["checked"] == ["001", "002", "003", "005", "006"]
    problems = [(item["task"], item["field"], item["problem"]) for item in report["board"]]
    assert ("5", "id", "编号与任务 005 重复") in problems
    assert ("001", "dependencies", "依赖成环：001 → 003 → 002 → 001") in problems
    assert ("006", "dependencies", "依赖成环：006 → 006") in problems
    stalled = [text for task, field, text in problems if task == "005"]
    assert len(stalled) == 1 and "#004" in stalled[0] and "集成记录" in stalled[0]
    assert len(problems) == 4


def test_validate_command_reports_without_writing(project, tmp_path):
    def validate(root, *args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), "validate", *args],
                              cwd=root, capture_output=True, text=True)

    save_plan(project, plan_task("001"))
    passed = validate(project)
    assert passed.returncode == 0 and "规划检查通过：1 个" in passed.stdout
    save_plan(project, plan_task("001"), plan_task("002", role="backend", acceptance=[]))
    before = {path: path.stat().st_mtime_ns for path in project.rglob("*") if path.is_file()}
    failed = validate(project)
    assert failed.returncode == 1
    assert "002 acceptance" in failed.stdout and "backend（任务 002）" in failed.stdout
    report = json.loads(validate(project, "--json").stdout)
    assert report["ok"] is False and report["checked"] == ["001", "002"]
    after = {path: path.stat().st_mtime_ns for path in project.rglob("*") if path.is_file()}
    assert after == before
    empty = tmp_path / "empty"
    empty.mkdir()
    result = validate(empty)
    assert result.returncode == 1 and "任务板没有任务" in result.stdout
    assert not list(empty.iterdir())


def git_project(project):
    git(project, "init", "-q")
    (project / "README.md").write_text("readme\n")
    (project / "dirty.txt").write_text("committed\n")
    git(project, "add", "README.md", "dirty.txt")
    git(project, "commit", "-qm", "test: record baseline")
    # Dirty before the run and left alone: the run must not be blamed for it.
    (project / "dirty.txt").write_text("edited by the user before dispatch\n")
    (project / "notes.txt").write_text("untracked before dispatch\n")
    return Workflow(project)


def test_changes_outside_declared_files_are_reported_and_must_be_explained(project, tmp_path):
    workflow = git_project(project)
    execution_id = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    (project / "stray.txt").write_text("written outside files")
    (project / "README.md").write_text("rewritten\n")
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "page.pyc").write_text("cache")
    (project / "planning" / "acceptance-002.json").write_text("{}")  # The main agent's own notes.
    workflow.finish(execution_id, "returned")
    report = workflow.inspect(execution_id)
    assert report["added"] == ["page.txt"]
    assert report["undeclared"] == {"checked": True, "head_moved": False, "paths": ["README.md", "stray.txt"]}
    assert len(report["notices"]) == 1 and "2 个声明范围外的路径" in report["notices"][0]
    record = workflow.history._load_record(execution_id)
    assert record.details["worktree"] is None
    audited(workflow, execution_id, tmp_path)
    with pytest.raises(ValueError, match="undeclared"):
        workflow.accept(execution_id, evidence())
    with pytest.raises(ValueError, match="undeclared"):
        workflow.accept(execution_id, {**evidence(), "undeclared": "  "})
    assert workflow.board.get_task("001")["status"] == "AWAITING_REVIEW"
    workflow.accept(execution_id, {**evidence(), "undeclared": "stray.txt 是子 Agent 的草稿，已删除；README 已还原"})
    accepted = workflow.history._load_record(execution_id).details["acceptance"]
    assert accepted["status"] == "passed" and "已还原" in accepted["undeclared"]


def test_clean_run_in_git_needs_no_explanation_and_staging_is_not_a_change(project, tmp_path):
    workflow = git_project(project)
    execution_id = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    git(project, "add", "notes.txt")
    workflow.finish(execution_id, "returned")
    report = workflow.inspect(execution_id)
    assert report["undeclared"] == {"checked": True, "head_moved": False, "paths": []}
    assert report["notices"] == []
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())


def test_committing_other_work_while_a_run_is_in_flight_is_not_an_undeclared_change(project, tmp_path):
    workflow = git_project(project)
    execution_id = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    git(project, "add", "notes.txt", "dirty.txt")
    git(project, "commit", "-qm", "test: commit earlier work while the worker runs")
    workflow.finish(execution_id, "returned")
    report = workflow.inspect(execution_id)
    assert report["undeclared"] == {"checked": True, "head_moved": True, "paths": []}
    assert len(report["notices"]) == 1 and "HEAD" in report["notices"][0]
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())


def test_inspect_says_when_declared_files_did_not_change_or_scope_was_not_checked(project):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    assert "notices" not in workflow.inspect(execution_id)  # Still running: nothing to conclude yet.
    workflow.finish(execution_id, "returned")
    report = workflow.inspect(execution_id)
    assert report["undeclared"] == {"checked": False, "paths": [], "head_moved": False}
    assert len(report["notices"]) == 2
    assert "没有任何变化" in report["notices"][0] and "没有检查声明范围外" in report["notices"][1]
    assert workflow.history._load_record(execution_id).details["dispatch_outcome"] == "returned"


def test_commit_during_a_run_and_deleted_or_reverted_files_are_reported(project, tmp_path):
    workflow = git_project(project)
    execution_id = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    git(project, "commit", "-qm", "test: commit made while the worker ran", "README.md", "--allow-empty")
    (project / "README.md").unlink()
    git(project, "checkout", "--", "dirty.txt")
    workflow.finish(execution_id, "returned")
    undeclared = workflow.inspect(execution_id)["undeclared"]
    assert undeclared == {"checked": True, "head_moved": True, "paths": ["README.md", "dirty.txt"]}


def test_parallel_runs_do_not_blame_each_other_but_report_writes_into_idle_tasks(project):
    workflow = git_project(project)
    document = workflow.board.get_document()
    document["tasks"].append({**document["tasks"][0], "id": "002", "files": ["other.txt"]})
    document["tasks"].append({**document["tasks"][0], "id": "003", "files": ["later.txt"]})
    workflow.board.save_document(document)
    first = workflow.begin("001")["execution_id"]
    second = workflow.begin("002")["execution_id"]
    (project / "page.txt").write_text("001")
    (project / "other.txt").write_text("002")
    workflow.finish(first, "returned")
    (project / "later.txt").write_text("written into a task nobody dispatched")
    workflow.finish(second, "returned")
    assert workflow.inspect(first)["undeclared"]["paths"] == []
    assert workflow.inspect(second)["undeclared"]["paths"] == ["later.txt"]


def test_retry_keeps_reporting_strays_the_previous_run_left_behind(project, tmp_path):
    workflow = git_project(project)
    first = workflow.begin("001")["execution_id"]
    (project / "stray.txt").write_text("left by the first run")
    workflow.finish(first, "failed")
    workflow.retry(first, "只写了范围外的 stray.txt，页面没做")
    second = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    workflow.finish(second, "returned")
    assert workflow.inspect(second)["undeclared"]["paths"] == ["stray.txt"]
    (project / "stray.txt").unlink()
    workflow.retry(second, "删除了 stray.txt，补充文案")
    third = workflow.begin("001")["execution_id"]
    workflow.finish(third, "returned")
    assert workflow.inspect(third)["undeclared"]["paths"] == []


def test_project_inside_a_larger_repository_reports_its_own_paths_or_admits_it_cannot(project, tmp_path):
    git(tmp_path, "init", "-q")
    workflow = Workflow(project)
    first = workflow.begin("001")["execution_id"]
    (project / "page.txt").write_text("中文")
    (project / "sub").mkdir()
    (project / "sub" / "中文 stray.txt").write_text("x")
    (tmp_path / "sibling.txt").write_text("outside the project")
    workflow.finish(first, "failed")
    assert workflow.inspect(first)["undeclared"] == {"checked": True, "head_moved": False,
                                                     "paths": ["sub/中文 stray.txt"]}
    (tmp_path / ".gitignore").write_text("project/\n")
    workflow.retry(first, "页面未完成")
    second = workflow.begin("001")["execution_id"]
    (project / "another.txt").write_text("git status cannot see this")
    workflow.finish(second, "returned")
    assert workflow.inspect(second)["undeclared"]["checked"] is False


@pytest.mark.parametrize(("worker", "expected"), [
    ("completed", "returned"), (None, "returned"),
    ("permission_rejected", "permission_rejected"), ("error", "failed"),
])
def test_runner_reports_how_the_worker_ended_not_only_the_dispatcher(project, worker, expected):
    class Returned:
        pid = 123
        returncode = 0

        def __init__(self, argv):
            self.argv = argv

        def communicate(self, timeout=None):
            settings = Path(self.argv[self.argv.index("--settings") + 1])
            (settings.parent.parent / "state" / "dispatcher").write_text("dispatcher")
            events = ({"type": "system", "session_id": "dispatcher"}, {"type": "completion", "is_error": False})
            return "\n".join(json.dumps(event) for event in events), ""

        def poll(self):
            return self.returncode

    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_capabilities"), patch("lib.runner.verify_receipt"), \
         patch("lib.workflow.worktree_state", return_value=None), \
         patch("lib.runner.check_team", return_value=[{"role": "frontend", "ok": True}]), \
         patch("lib.runner.subprocess.Popen", side_effect=lambda argv, **_: Returned(argv)) as popen, \
         patch("lib.workflow.audit_runs", return_value=[{"actual": "custom:proxy/claude", "outcome": worker}]):
        result = run_task(project, "001", "custom:dispatcher")
    argv = popen.call_args[0][0]
    assert argv[argv.index("--auto") + 1] == "medium"
    assert result["audit"]["status"] == "passed"
    assert result["dispatch_outcome"] == expected
    assert result["transport"]["worker_outcome"] == worker
    assert ExecutionHistory(project).get_all_history()[0].details["dispatch_outcome"] == expected


def test_receipt_from_another_autonomy_level_requires_a_new_preflight(project):
    from lib import probe
    receipt = project / ".task-management" / "sandbox-probe.json"
    data = {"ok": True, "dispatcher": "custom:dispatcher", "executable": "fp",
            "policy": probe.policy_fingerprint(project), "autonomy": "medium"}
    with patch("lib.probe.fingerprint", return_value="fp"):
        receipt.write_text(json.dumps(data))
        verify_receipt(project, "custom:dispatcher", "droid")
        for stale in ({**data, "autonomy": "low"}, {k: v for k, v in data.items() if k != "autonomy"}):
            receipt.write_text(json.dumps(stale))
            with pytest.raises(ValueError, match="重新运行 foreman preflight"):
                verify_receipt(project, "custom:dispatcher", "droid")


def direct_project(project, **fields):
    """One task without a role: the current session does it instead of a dispatched worker."""
    task = plan_task("001", **fields)
    del task["role"]
    save_plan(project, task)
    return Workflow(project)


def test_task_without_role_is_done_by_the_current_session_under_the_same_gates(project):
    workflow = direct_project(project)
    assert check_plan(project) == {"ok": True, "checked": ["001"], "direct": ["001"], "board": [], "team": []}
    plan = workflow.begin("001")
    execution_id = plan["execution_id"]
    assert plan["mode"] == "direct" and "task_args" not in plan and execution_id in plan["instruction"]
    assert "实现页面" in plan["context"]
    record = workflow.history._load_record(execution_id)
    assert (record.droid, record.model) == ("current-session", None)
    assert record.details["audit"] == {"status": "not_applicable"}
    with pytest.raises(ValueError, match="completed"):
        workflow.finish(execution_id, "returned")
    with pytest.raises(ValueError, match="finish"):
        workflow.accept(execution_id, evidence())
    (project / "page-001.txt").write_text("中文")
    workflow.finish(execution_id, "completed")
    workflow.finish(execution_id, "completed")  # Idempotent.
    report = workflow.inspect(execution_id)
    assert (report["mode"], report["dispatch_outcome"], report["added"]) == ("direct", "completed", ["page-001.txt"])
    assert workflow.audit(execution_id) == {"status": "not_applicable"}
    with pytest.raises(ValueError, match="全部验收条件"):
        workflow.accept(execution_id, {"inspection": "看过", "checks": []})
    assert workflow.board.get_task("001")["status"] == "AWAITING_REVIEW"
    workflow.accept(execution_id, evidence())
    accepted = workflow.history._load_record(execution_id)
    assert accepted.status == "success" and accepted.details["acceptance"]["self_review"] is True
    assert workflow.board.get_task("001")["status"] == "AWAITING_INTEGRATION"
    workflow.integration_ready("001")
    (project / "page-001.txt").write_text("验收后又改了")
    with pytest.raises(ValueError, match="文件已变化"):
        workflow.integration_ready("001")


def test_completed_is_not_a_dispatch_outcome(project, tmp_path):
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    with pytest.raises(ValueError, match="completed"):
        workflow.finish(execution_id, "completed")
    assert workflow.history._load_record(execution_id).status == "running"
    assert workflow.inspect(execution_id)["mode"] == "dispatch"
    workflow.finish(execution_id, "returned")
    audited(workflow, execution_id, tmp_path)
    workflow.accept(execution_id, evidence())
    assert workflow.history._load_record(execution_id).details["acceptance"]["self_review"] is False


def test_run_refuses_a_task_without_role_before_recording_anything(project):
    direct_project(project)
    with patch("lib.runner.list_byok_models", return_value=[{"id": "custom:dispatcher"}]), \
         patch("lib.runner.check_capabilities"), \
         pytest.raises(ValueError, match="当前会话直接执行"):
        run_task(project, "001", "custom:dispatcher")
    assert not ExecutionHistory(project).get_all_history()
    assert TaskBoard.load(project).get_task("001")["status"] == "PENDING"


def test_direct_execution_reports_stray_edits_and_integrates_through_the_cli(project):
    git_project(project)
    direct_project(project)

    def cli(*args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=project, capture_output=True, text=True)

    started = cli("execution", "begin", "001")
    assert started.returncode == 0, started.stderr
    execution_id = json.loads(started.stdout)["execution_id"]
    (project / "page-001.txt").write_text("中文\n")
    (project / "stray.txt").write_text("顺手改的")
    assert cli("execution", "finish", execution_id, "--outcome", "returned").returncode == 1
    assert cli("execution", "finish", execution_id, "--outcome", "completed").returncode == 0
    report = json.loads(cli("execution", "inspect", execution_id).stdout)
    assert report["undeclared"]["paths"] == ["stray.txt"]
    assert len(report["notices"]) == 1 and report["notices"][0].startswith("执行期间有 1 个")
    assert cli("execution", "audit", execution_id).returncode == 0
    proof = project / "planning" / "acceptance-001.json"
    proof.write_text(json.dumps(evidence()), encoding="utf-8")
    refused = cli("execution", "accept", execution_id, "--evidence-file", str(proof))
    assert refused.returncode == 1 and "执行期间有声明范围外的改动" in refused.stderr
    (project / "stray.txt").unlink()
    proof.write_text(json.dumps({**evidence(), "undeclared": "stray.txt 是草稿，已删除"}), encoding="utf-8")
    accepted = cli("execution", "accept", execution_id, "--evidence-file", str(proof))
    assert accepted.returncode == 0, accepted.stderr
    assert cli("update", "001", "DONE").returncode == 1
    git(project, "add", "page-001.txt")
    git(project, "commit", "-qm", "test: record direct work")
    commit = git(project, "rev-parse", "HEAD").stdout.strip()
    integrated = cli("integrate", "001", "--commit", commit)
    assert integrated.returncode == 0, integrated.stderr
    assert TaskBoard.load(project).get_task("001")["status"] == "DONE"


def test_direct_execution_can_be_interrupted_and_reworked(project):
    workflow = direct_project(project)
    first = workflow.begin("001")["execution_id"]
    (project / "page-001.txt").write_text("一半")
    with pytest.raises(ValueError, match="明确 retry"):
        workflow.begin("001")
    workflow.finish(first, "interrupted")
    workflow.retry(first, "只写了一半；保留已有内容，补完错误提示")
    second = workflow.begin("001")
    assert second["mode"] == "direct" and second["execution_id"] != first
    assert "补完错误提示" in second["context"]
    assert (project / "page-001.txt").read_text() == "一半"


def test_add_writes_every_task_or_none(project):
    board = TaskBoard.load(project)
    assert board.add_tasks([plan_task("002"), {"id": "003", "title": "文档", "dependencies": ["002"]}]) == ["002", "003"]
    added = board.get_task("003")
    assert (added["status"], added["dependencies"]) == ("PENDING", "#002")
    before = board.get_document()
    for bad in ([plan_task("004"), plan_task("2")],  # 2 is the same task as 002.
                [plan_task("004"), plan_task("004")],
                [plan_task("004", status="DONE")],
                [plan_task("004", execution_id="004-made-up")],
                [plan_task("004", integration={"commit": "abc"})],
                [{"id": "004"}], [{"id": 4, "title": "编号不是字符串"}],
                [{"id": "../x", "title": "编号不能当文件名"}], ["004"]):
        with pytest.raises(ValueError):
            board.add_tasks(bad)
    assert board.get_document() == before

    board.add_tasks([plan_task("002", title="改过的标题")], replace=True)
    assert board.get_task("002")["title"] == "改过的标题" and len(board.get_all_tasks()) == 3
    workflow = Workflow(project)
    execution_id = workflow.begin("001")["execution_id"]
    with pytest.raises(ValueError, match="正在进行"):
        board.add_tasks([{"id": "001", "title": "改写进行中的任务"}], replace=True)
    assert board.get_task("001")["execution_id"] == execution_id
    # Waiting for rework: the plan may change, the rework trail may not be dropped.
    workflow.finish(execution_id, "failed")
    workflow.retry(execution_id, "漏了 extra.txt")
    board.add_tasks([{
        "id": "001", "title": "页面", "role": "frontend", "files": ["page.txt", "extra.txt"],
        "runtime_dependencies": ["page.txt"],
        "acceptance": [{"id": "copy", "scenario": "打开页面", "expected": "显示中文", "method": "manual"}],
    }], replace=True)
    reworked = board.get_task("001")
    assert (reworked["execution_id"], reworked["failed_attempts"], reworked["last_failure"]) == (
        execution_id, 1, "漏了 extra.txt")
    assert workflow.begin("001")["files"] == ["page.txt", "extra.txt"]


def test_add_and_show_commands(tmp_path):
    project = tmp_path / "fresh"
    project.mkdir()

    def cli(*args, stdin=None):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=project, capture_output=True, text=True, input=stdin)

    assert cli("init").returncode == 0
    direct = plan_task("001")
    del direct["role"]
    plan = project / "planning" / "plan.json"
    plan.write_text(json.dumps({"tasks": [direct, plan_task("002", dependencies=["001"])]}), encoding="utf-8")
    added = cli("add", "--file", str(plan))
    assert added.returncode == 0 and "001、002" in added.stdout, added.stderr
    again = cli("add", "--file", str(plan))
    assert again.returncode == 1 and "已存在" in again.stderr
    assert cli("add", "--file", "-", stdin=json.dumps(plan_task("003", title="从标准输入"))).returncode == 0

    listing = cli("show").stdout.splitlines()
    assert listing[0].split("\t") == ["001", "PENDING", "当前会话直接执行", "页面"]
    assert listing[1].split("\t") == ["002", "PENDING", "派给角色 frontend", "页面", "等待 #001"]
    assert [task["id"] for task in json.loads(cli("show", "--json").stdout)] == ["001", "002", "003"]
    context = cli("show", "001").stdout
    assert "实现页面" in context and "page-001.txt" in context and "执行: 当前会话直接执行" in context
    assert json.loads(cli("show", "001", "--json").stdout)["files"] == ["page-001.txt"]
    assert cli("show", "404").returncode == 1
    assert cli("show", "--mermaid").stdout.splitlines() == [
        "graph TD", '  001["001: 页面"]', '  002["002: 页面"]', "  001 --> 002", '  003["003: 从标准输入"]']
    assert "执行: 当前会话直接执行" in cli("select").stdout
    checked = cli("validate")
    assert checked.returncode == 1 and "其中 1 个没有 role，由当前会话直接执行：001" in checked.stdout
    assert "frontend（任务 002、003）" in checked.stdout


def test_select_only_offers_a_task_that_can_start(project):
    tasks = [plan_task("001"), plan_task("002"), plan_task("003", dependencies=["001"])]
    for task in tasks:
        del task["role"]
    save_plan(project, *tasks)

    def cli(*args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=project, capture_output=True, text=True)

    assert cli("select").stdout.startswith("下一个任务: 001 ")
    assert cli("execution", "begin", "001").returncode == 0
    # A started task is no longer on offer: select names what batch would start.
    assert cli("select").stdout.startswith("下一个任务: 002 ")
    assert cli("execution", "begin", "002").returncode == 0
    assert cli("select").stdout.splitlines() == [
        "没有可以开始的任务", "未完成: 001 IN_PROGRESS - 页面", "未完成: 002 IN_PROGRESS - 页面",
        "跳过: 003 - 依赖未完成: #001"]
    save_plan(project, {"id": "001", "title": "旧任务", "status": "DONE"})
    assert cli("select").stdout == "所有任务都已完成\n"
    save_plan(project)
    assert cli("select").stdout == "任务板没有任务\n"


def test_cli_finds_the_project_root_from_a_subdirectory(project):
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)

    def cli(*args, cwd=nested):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=cwd, capture_output=True, text=True)

    shown = cli("show")
    assert shown.stdout.startswith("001\tPENDING") and f"项目根目录: {project.resolve()}" in shown.stderr
    assert cli("acceptance", "001").returncode == 0
    assert not (nested / "planning").exists() and not (nested / ".task-management").exists()
    # A repository inside the project is a boundary: it is a project of its own.
    inner = project / "vendor" / "lib"
    inner.mkdir(parents=True)
    git(inner, "init", "-q")
    lost = cli("show", cwd=inner)
    assert lost.stdout == "任务板没有任务\n" and "没有任务板或配置" in lost.stderr and "init" in lost.stderr
    created = cli("init")
    assert created.returncode == 0 and f"上级目录 {project.resolve()} 已有任务板" in created.stderr
    assert cli("show").stdout == "任务板没有任务\n"


def test_next_steps_lead_a_direct_task_through_the_cli_by_task_id(project):
    git_project(project)
    direct_project(project)
    nested = project / "src"
    nested.mkdir()

    def cli(*args):
        return subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), *args],
                              cwd=nested, capture_output=True, text=True)

    def steps():
        return cli("show", "001").stdout.split("## 下一步", 1)[1].splitlines()[1:]

    assert steps() == ["foreman execution begin 001   # 登记开始，然后由当前会话实现"]
    assert cli("execution", "begin", "001").returncode == 0
    assert steps()[1].startswith("foreman execution finish 001 --outcome completed")
    (project / "page-001.txt").write_text("中文\n")
    (project / "stray.txt").write_text("顺手改的")
    finished = cli("execution", "finish", "001", "--outcome", "completed")
    assert finished.returncode == 0, finished.stderr
    assert "foreman acceptance 001 --template   # 生成 planning/acceptance-001.json，逐项填写证据" in steps()
    assert json.loads(cli("execution", "inspect", "1").stdout)["undeclared"]["paths"] == ["stray.txt"]
    made = cli("acceptance", "001", "--template")
    assert made.returncode == 0 and "stray.txt" in made.stdout
    proof = project / "planning" / "acceptance-001.json"
    assert json.loads(proof.read_text(encoding="utf-8")) == {"inspection": "", "undeclared": "", "checks": [{
        "id": "copy", "status": "", "evidence": "", "scenario": "打开页面", "expected": "显示中文",
        "method": "manual"}]}
    # Submitted unfilled, the template is refused instead of being recorded as a pass.
    refused = cli("execution", "accept", "001", "--evidence-file", "planning/acceptance-001.json")
    assert refused.returncode == 1 and "审查结论" in refused.stderr
    assert cli("acceptance", "001", "--template").returncode == 1  # Filled-in work is not overwritten.
    proof.write_text(json.dumps({**evidence(), "undeclared": "stray.txt 是草稿，留在工作区不提交"}), encoding="utf-8")
    assert "编辑 planning/acceptance-001.json，逐项填写证据" in steps()
    accepted = cli("execution", "accept", "001", "--evidence-file", "planning/acceptance-001.json")
    assert accepted.returncode == 0, accepted.stderr
    assert steps()[-1] == "foreman integrate 001 --commit <提交 SHA>"
    missing = cli("execution", "inspect", "002")
    assert missing.returncode == 1 and "找不到执行记录或任务 002" in missing.stderr


def test_next_steps_for_a_dispatched_task_follow_its_record(project, tmp_path):
    workflow = Workflow(project)

    def steps():
        shown = subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), "show", "001"],
                               cwd=project, capture_output=True, text=True)
        return shown.stdout.split("## 下一步", 1)[1]

    assert "foreman run 001 --dispatcher <调度模型ID>" in steps()
    execution_id = workflow.begin("001")["execution_id"]
    assert "foreman execution finish 001 --outcome returned" in steps()
    workflow.finish(execution_id, "returned")
    assert "foreman execution audit 001" in steps()
    audited(workflow, execution_id, tmp_path)
    assert "execution audit" not in steps() and "foreman execution accept 001" in steps()
    workflow.retry(execution_id, "实际模型不可用", block=True)
    assert "foreman execution unblock 001 --reason" in steps()
    workflow.unblock(execution_id, "用户已恢复模型服务")
    assert "foreman run 001 --dispatcher <调度模型ID>" in steps()


def test_evidence_template_refuses_a_task_id_that_cannot_name_a_file(project):
    # save_document skips the id check that add applies, like a board edited by hand.
    save_plan(project, plan_task("../../../escape"))
    made = subprocess.run([sys.executable, str(SKILL / "tools/cli.py"), "acceptance", "../../../escape", "--template"],
                          cwd=project, capture_output=True, text=True)
    assert made.returncode == 1 and "不能用作文件名" in made.stderr
    assert not (project / "escape.json").exists() and not (project / "planning" / "acceptance-..").exists()
