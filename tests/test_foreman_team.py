"""Tests for foreman fixed-model team, role routing and parallel batches."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).parent.parent / "foreman"
# 以 lib 包导入：其他测试会把 skill/scripts 放进 sys.path，那里也有 config.py
sys.path.insert(0, str(SKILL_ROOT))

from lib.board import TaskBoard  # noqa: E402
from lib.config import ExecutionConfig  # noqa: E402
from lib.executor import TaskExecutor  # noqa: E402
from lib.store import select_parallel_batch, write_tasks_document  # noqa: E402
from lib.team import (  # noqa: E402
    MANAGED_MARKER,
    TeamError,
    audit_runs,
    check_team,
    configure_role,
    list_byok_models,
    remove_role,
)

SECRET = "fake-api-key-for-tests"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _task(task_id, files=None, status="PENDING", deps="无", role=None, priority=1):
    task = {"id": task_id, "title": f"任务{task_id}", "status": status, "priority": priority,
            "dependencies": deps, "sections": []}
    if files is not None:
        task["files"] = files
    if role:
        task["role"] = role
    return task


def _ids(result):
    return [task["id"] for task in result["batch"]]


class TestParallelBatch(unittest.TestCase):
    def test_disjoint_files_run_together_up_to_limit(self):
        doc = {"tasks": [_task("001", ["src/a.py"]), _task("002", ["src/b.py"]), _task("003", ["src/c.py"])]}
        result = select_parallel_batch(doc, max_parallel=2)
        self.assertEqual(_ids(result), ["001", "002"])
        self.assertIn("并发上限", result["skipped"][0]["reason"])

    def test_overlapping_files_are_not_batched(self):
        doc = {"tasks": [_task("001", ["src/app.py"]), _task("002", ["src/app.py", "src/x.py"])]}
        result = select_parallel_batch(doc, max_parallel=3)
        self.assertEqual(_ids(result), ["001"])
        self.assertIn("重叠", result["skipped"][0]["reason"])

    def test_directory_and_glob_scopes_overlap_with_contained_files(self):
        doc = {"tasks": [_task("001", ["frontend/"]), _task("002", ["frontend/src/App.tsx"]),
                         _task("003", ["backend/**/*.py"]), _task("004", ["backend/api/users.py"])]}
        self.assertEqual(_ids(select_parallel_batch(doc, max_parallel=4)), ["001", "003"])

    def test_similar_prefix_is_not_overlap(self):
        doc = {"tasks": [_task("001", ["src/app"]), _task("002", ["src/application.py"])]}
        self.assertEqual(_ids(select_parallel_batch(doc, max_parallel=2)), ["001", "002"])

    def test_task_without_files_runs_alone(self):
        doc = {"tasks": [_task("001", None), _task("002", ["src/b.py"])]}
        result = select_parallel_batch(doc, max_parallel=2)
        self.assertEqual(_ids(result), ["001"])
        doc = {"tasks": [_task("001", ["src/a.py"]), _task("002", None)]}
        self.assertEqual(_ids(select_parallel_batch(doc, max_parallel=2)), ["001"])

    def test_unmet_dependency_is_skipped(self):
        doc = {"tasks": [_task("001", ["a.py"], status="AWAITING_REVIEW"), _task("002", ["b.py"], deps="#001")]}
        result = select_parallel_batch(doc)
        self.assertEqual(_ids(result), [])
        self.assertIn("#001", result["skipped"][0]["reason"])

    def test_done_dependency_requires_integration(self):
        done = _task("001", ["a.py"], status="DONE")
        doc = {"tasks": [done, _task("002", ["b.py"], deps="#001")]}
        self.assertEqual(_ids(select_parallel_batch(doc)), [])
        done["integration"] = {"commit": "abc"}
        self.assertEqual(_ids(select_parallel_batch(doc)), ["002"])

    def test_active_task_files_block_new_work(self):
        doc = {"tasks": [_task("001", ["src/a.py"], status="IN_PROGRESS"), _task("002", ["src/a.py"]),
                         _task("003", ["src/b.py"])]}
        self.assertEqual(_ids(select_parallel_batch(doc)), ["003"])

    def test_active_task_without_files_blocks_everything(self):
        doc = {"tasks": [_task("001", None, status="IN_PROGRESS"), _task("002", ["src/b.py"])]}
        self.assertEqual(_ids(select_parallel_batch(doc)), [])

    def test_blocked_task_without_files_does_not_stall_board(self):
        doc = {"tasks": [_task("001", None, status="BLOCKED"), _task("002", ["src/b.py"])]}
        self.assertEqual(_ids(select_parallel_batch(doc)), ["002"])

    def test_unconfigured_role_is_skipped(self):
        doc = {"tasks": [_task("001", ["a.py"], role="frontend"), _task("002", ["b.py"], role="backend")]}
        result = select_parallel_batch(doc, roles={"backend": {}})
        self.assertEqual(_ids(result), ["002"])
        self.assertIn("frontend", result["skipped"][0]["reason"])

    def test_legacy_open_status_is_ready(self):
        doc = {"tasks": [_task("001", ["a.py"], status="OPEN")]}
        self.assertEqual(_ids(select_parallel_batch(doc)), ["001"])


class TeamTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "project"
        self.root.mkdir()
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.open_port = self.listener.getsockname()[1]
        self.closed_port = _free_port()
        self.settings = Path(self.temp_dir.name) / "settings.json"
        self.settings.write_text(json.dumps({"customModels": [
            {"model": "fast-model", "id": "custom:fast-model-0", "displayName": "Fast",
             "baseUrl": f"http://127.0.0.1:{self.open_port}/v1", "apiKey": SECRET, "provider": "openai"},
            {"model": "down-model", "id": "custom:proxy/down-model", "displayName": "Down",
             "baseUrl": f"http://127.0.0.1:{self.closed_port}", "apiKey": SECRET, "provider": "anthropic"},
            {"model": "no-id-model", "displayName": "Legacy", "baseUrl": "", "apiKey": SECRET},
        ]}), encoding="utf-8")

    def tearDown(self):
        self.listener.close()
        self.temp_dir.cleanup()

    def droid_file(self, role):
        return self.root / ".factory" / "droids" / f"tm-{role}.md"


class TestTeam(TeamTestCase):
    def test_list_models_hides_secrets(self):
        models = list_byok_models(self.settings)
        self.assertEqual([m["id"] for m in models],
                         ["custom:fast-model-0", "custom:proxy/down-model", "custom:no-id-model"])
        self.assertNotIn(SECRET, json.dumps(models))
        self.assertEqual(models[0]["endpoint"], f"127.0.0.1:{self.open_port}")

    def test_configure_role_writes_droid_and_config(self):
        path = configure_role(self.root, "frontend", "custom:fast-model-0", "页面和组件: React",
                              settings_path=self.settings)
        text = path.read_text(encoding="utf-8")
        self.assertIn("name: tm-frontend\n", text)
        self.assertIn("model: custom:fast-model-0\n", text)
        self.assertIn('description: "页面和组件: React"', text)
        self.assertNotIn("tools:", text)
        self.assertIn(MANAGED_MARKER, text)
        role = ExecutionConfig(self.root).get_role("frontend")
        self.assertEqual(role["droid"], "tm-frontend")
        self.assertEqual(role["model"], "custom:fast-model-0")

    def test_read_only_role(self):
        path = configure_role(self.root, "reviewer", "custom:fast-model-0", "审查", read_only=True,
                              settings_path=self.settings)
        self.assertIn("tools: read-only\n", path.read_text(encoding="utf-8"))

    def test_rejects_unknown_model_and_bad_role(self):
        with self.assertRaises(TeamError):
            configure_role(self.root, "frontend", "custom:not-configured", "x", settings_path=self.settings)
        with self.assertRaises(TeamError):
            configure_role(self.root, "Front End", "custom:fast-model-0", "x", settings_path=self.settings)
        self.assertFalse((self.root / ".factory").exists())

    def test_does_not_overwrite_user_droid_without_force(self):
        path = self.droid_file("backend")
        path.parent.mkdir(parents=True)
        path.write_text("---\nname: tm-backend\nmodel: inherit\n---\n\nmine\n", encoding="utf-8")
        with self.assertRaises(TeamError):
            configure_role(self.root, "backend", "custom:fast-model-0", "接口", settings_path=self.settings)
        self.assertIn("mine", path.read_text(encoding="utf-8"))
        configure_role(self.root, "backend", "custom:fast-model-0", "接口", force=True, settings_path=self.settings)
        self.assertIn(MANAGED_MARKER, path.read_text(encoding="utf-8"))

    def test_reconfigure_switches_model(self):
        configure_role(self.root, "qa", "custom:fast-model-0", "测试", settings_path=self.settings)
        configure_role(self.root, "qa", "custom:proxy/down-model", "测试", settings_path=self.settings)
        self.assertIn("model: custom:proxy/down-model\n", self.droid_file("qa").read_text(encoding="utf-8"))
        self.assertEqual(ExecutionConfig(self.root).get_role("qa")["model"], "custom:proxy/down-model")

    def test_remove_role_keeps_unmanaged_files(self):
        configure_role(self.root, "qa", "custom:fast-model-0", "测试", settings_path=self.settings)
        self.assertTrue(remove_role(self.root, "qa"))
        self.assertFalse(self.droid_file("qa").exists())
        self.assertIsNone(ExecutionConfig(self.root).get_role("qa"))

    def test_check_team_reports_unreachable_and_drift(self):
        configure_role(self.root, "frontend", "custom:fast-model-0", "页面", settings_path=self.settings)
        configure_role(self.root, "backend", "custom:proxy/down-model", "接口", settings_path=self.settings)
        configure_role(self.root, "qa", "custom:fast-model-0", "测试", settings_path=self.settings)
        qa = self.droid_file("qa")
        qa.write_text(qa.read_text(encoding="utf-8").replace("custom:fast-model-0", "inherit"), encoding="utf-8")

        results = {item["role"]: item for item in check_team(self.root, settings_path=self.settings, timeout=1)}
        self.assertTrue(results["frontend"]["ok"])
        self.assertFalse(results["backend"]["ok"])
        self.assertIn(f"127.0.0.1:{self.closed_port}", results["backend"]["problems"][0])
        self.assertFalse(results["qa"]["ok"])
        self.assertIn("不一致", results["qa"]["problems"][0])

    def test_check_team_reports_removed_model(self):
        configure_role(self.root, "frontend", "custom:fast-model-0", "页面", settings_path=self.settings)
        self.settings.write_text(json.dumps({"customModels": []}), encoding="utf-8")
        result = check_team(self.root, settings_path=self.settings)[0]
        self.assertFalse(result["ok"])
        self.assertIn("不在 BYOK", result["problems"][0])

    def test_audit_runs_compares_expected_and_actual(self):
        configure_role(self.root, "frontend", "custom:fast-model-0", "页面", settings_path=self.settings)
        configure_role(self.root, "backend", "custom:proxy/down-model", "接口", settings_path=self.settings)
        sessions = Path(self.temp_dir.name) / "sessions"
        folder = sessions / str(self.root.resolve()).replace("/", "-")
        folder.mkdir(parents=True)

        def session(sid, title, model, calling=True):
            start = {"type": "session_start", "id": sid, "title": title}
            if calling:
                start["callingSessionId"] = "parent"
            (folder / f"{sid}.jsonl").write_text(json.dumps(start) + "\n", encoding="utf-8")
            (folder / f"{sid}.settings.json").write_text(json.dumps({"model": model}), encoding="utf-8")

        session("s1", "Tm-frontend: 任务 001: 页面", "custom:fast-model-0")
        with (folder / "s1.jsonl").open("a", encoding="utf-8") as handle:
            for reason in ("completed", "permission_rejected"):
                handle.write(json.dumps({"type": "agent_turn_outcome", "reason": reason}) + "\n")
        session("s2", "Tm-backend: 任务 002: 接口", "custom:proxy/strong-model")
        session("s3", "Main session", "custom:fast-model-0", calling=False)
        session("s4", "Worker: other", "custom:fast-model-0")

        records = {r["role"]: r for r in audit_runs(self.root, sessions_dir=sessions)}
        self.assertEqual(set(records), {"frontend", "backend"})
        self.assertTrue(records["frontend"]["ok"])
        self.assertFalse(records["backend"]["ok"])
        self.assertEqual(records["backend"]["actual"], "custom:proxy/strong-model")
        self.assertEqual(records["frontend"]["outcome"], "permission_rejected")
        self.assertIsNone(records["backend"]["outcome"])


class TestRoleRouting(TeamTestCase):
    def setUp(self):
        super().setUp()
        configure_role(self.root, "frontend", "custom:fast-model-0", "页面", settings_path=self.settings)
        configure_role(self.root, "backend", "custom:proxy/down-model", "接口", settings_path=self.settings)
        write_tasks_document({"tasks": [
            _task("001", ["web/App.tsx"], role="frontend", priority=3),
            _task("002", ["api/users.py"], role="backend", priority=2),
            dict(_task("003", ["docs/x.md"], priority=1), type="docs"),
            _task("004", ["web/App.tsx"], role="frontend", priority=1),
            _task("005", ["x.py"], role="designer", priority=1),
        ]}, self.root / "planning" / "tasks.md")

    def test_role_task_uses_fixed_droid_without_complexity(self):
        plan = TaskExecutor(self.root).plan_execution("001")
        self.assertEqual(plan["droid"], "tm-frontend")
        self.assertEqual(plan["model"], "custom:fast-model-0")
        self.assertEqual(plan["task_args"]["subagent_type"], "tm-frontend")
        self.assertNotIn("complexity", plan["task_args"])
        self.assertIn("web/App.tsx", plan["task_args"]["prompt"])

    def test_task_without_role_keeps_complexity_routing(self):
        plan = TaskExecutor(self.root).plan_execution("003")
        self.assertIsNone(plan["role"])
        self.assertEqual(plan["droid"], "worker")
        self.assertEqual(plan["task_args"]["complexity"], "light")

    def test_unconfigured_role_raises(self):
        with self.assertRaises(ValueError):
            TaskExecutor(self.root).plan_execution("005")

    def test_plan_batch_routes_each_task_to_its_model(self):
        plan = TaskExecutor(self.root).plan_batch()
        self.assertEqual([(p["task_id"], p["droid"]) for p in plan["batch"]],
                         [("001", "tm-frontend"), ("002", "tm-backend")])
        skipped = {s["id"]: s["reason"] for s in plan["skipped"]}
        self.assertIn("并发上限", skipped["003"])
        self.assertIn("designer", skipped["005"])

    def test_retry_limit_blocks_task(self):
        board = TaskBoard.load(self.root)
        self.assertEqual(board.record_failure("001", max_retries=2), (1, "PENDING"))
        self.assertEqual(board.record_failure("001", max_retries=2), (2, "PENDING"))
        self.assertEqual(board.record_failure("001", max_retries=2), (3, "BLOCKED"))
        board.update_task_status("001", "PENDING", reset_retries=True)
        self.assertEqual(board.get_task("001")["failed_attempts"], 0)
        self.assertEqual(board.record_failure("002", max_retries=2, block=True), (1, "BLOCKED"))


class TestConfigCompat(unittest.TestCase):
    def test_old_config_gets_new_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".task-management").mkdir()
            (root / ".task-management" / "config.json").write_text(
                json.dumps({"execution": {"light": "deepseek-worker"}}), encoding="utf-8")
            config = ExecutionConfig(root)
            self.assertEqual(config.get_droid_for_complexity("light"), "deepseek-worker")
            self.assertEqual(config.get_droid_for_complexity("heavy"), "worker")
            self.assertEqual(config.get_roles(), {})
            self.assertEqual(config.get_max_parallel(), 2)
            self.assertIn("by_type", config.get_all_settings()["complexity_rules"])

    def test_defaults_are_not_shared_between_instances(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = ExecutionConfig(Path(a))
            first.config["roles"]["x"] = {"droid": "tm-x"}
            self.assertEqual(ExecutionConfig(Path(b)).get_roles(), {})


class TestCli(TeamTestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SKILL_ROOT / "tools" / "cli.py"), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_cli_end_to_end(self):
        self.assertEqual(self.run_cli("init").returncode, 0)
        models = self.run_cli("models", "--settings", str(self.settings))
        self.assertEqual(models.returncode, 0, models.stderr)
        self.assertIn("custom:fast-model-0", models.stdout)
        self.assertNotIn(SECRET, models.stdout + models.stderr)

        created = self.run_cli("team", "set", "frontend", "--model", "custom:fast-model-0",
                               "--description", "页面", "--settings", str(self.settings))
        self.assertEqual(created.returncode, 0, created.stderr)
        bad = self.run_cli("team", "set", "backend", "--model", "custom:nope",
                           "--description", "接口", "--settings", str(self.settings))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("不在 BYOK", bad.stderr)

        check = self.run_cli("team", "check", "--json", "--settings", str(self.settings))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertTrue(json.loads(check.stdout)[0]["ok"])

        board = TaskBoard.load(self.root)
        document = board.get_document()
        document["tasks"] = [_task("001", ["web/a.tsx"], role="frontend"), _task("002", ["web/b.tsx"])]
        board.save_document(document)
        batch = self.run_cli("batch", "--json")
        self.assertEqual(batch.returncode, 0, batch.stderr)
        plan = json.loads(batch.stdout)
        self.assertEqual([(p["mode"], p["droid"]) for p in plan["batch"]],
                         [("dispatch", "tm-frontend"), ("direct", "current-session")])
        # Task arguments exist only for the task a sub-agent will do; the session does the other one itself.
        self.assertEqual(["task_args" in p for p in plan["batch"]], [True, False])

        failed = self.run_cli("fail", "001", "--block", "--reason", "模型服务不可用")
        self.assertEqual(failed.returncode, 0, failed.stderr)
        self.assertEqual(board.get_task("001")["status"], "BLOCKED")

        status = self.run_cli("status")
        self.assertEqual(status.returncode, 0, status.stderr)

    def test_cli_integrate_unlocks_dependents(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "a"],
                       cwd=self.root, check=True)
        board = TaskBoard.load(self.root)
        write_tasks_document({"tasks": [_task("001", ["a.txt"], status="AWAITING_INTEGRATION"),
                                        _task("002", ["b.txt"], deps="#001")]},
                             self.root / "planning" / "tasks.md")
        self.assertEqual(_ids(board.select_batch()), [])

        missing = self.run_cli("integrate", "001", "--commit", "deadbeef")
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(board.get_task("001")["status"], "AWAITING_INTEGRATION")

        done = self.run_cli("integrate", "001", "--commit", "HEAD", "--note", "ok")
        self.assertEqual(done.returncode, 0, done.stderr)
        task = board.get_task("001")
        self.assertEqual(task["status"], "DONE")
        self.assertEqual(len(task["integration"]["commit"]), 40)
        self.assertEqual(_ids(board.select_batch()), ["002"])


class TestLegacyTaskFile(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.planning = self.root / "planning"
        self.planning.mkdir()
        legacy = {"tasks": [_task("001", ["a.py"], status="PENDING")]}
        (self.planning / "codex-tasks.json").write_text(json.dumps(legacy), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_legacy_file_when_new_file_missing(self):
        board = TaskBoard.load(self.root)
        self.assertEqual(board.get_task("001")["status"], "PENDING")
        self.assertFalse((self.planning / "tasks.json").exists())

    def test_first_write_moves_data_to_new_file(self):
        board = TaskBoard.load(self.root)
        board.update_task_status("001", "IN_PROGRESS")
        saved = json.loads((self.planning / "tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["tasks"][0]["status"], "IN_PROGRESS")
        self.assertTrue((self.planning / "tasks.md").exists())
        self.assertTrue((self.planning / "codex-tasks.json").exists())

    def test_new_file_wins_over_legacy(self):
        write_tasks_document({"tasks": [_task("002", ["b.py"])]}, self.planning / "tasks.md")
        self.assertIsNone(TaskBoard.load(self.root).get_task("001"))
        self.assertIsNotNone(TaskBoard.load(self.root).get_task("002"))

    def test_cli_init_keeps_legacy_tasks(self):
        cli = SKILL_ROOT / "tools" / "cli.py"
        result = subprocess.run([sys.executable, str(cli), "init"], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads((self.planning / "tasks.json").read_text(encoding="utf-8"))
        self.assertEqual([t["id"] for t in saved["tasks"]], ["001"])


if __name__ == "__main__":
    unittest.main()
