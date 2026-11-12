"""Tests for foreman lib."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# 以 lib 包导入：其他测试会把 skill/scripts 放进 sys.path，那里也有 config.py
sys.path.insert(0, str(Path(__file__).parent.parent / "foreman"))

from lib.board import TaskBoard
from lib.checkpoint import CheckpointManager
from lib.config import ExecutionConfig
from lib.executor import TaskExecutor
from lib.history import ExecutionHistory
from lib.store import write_tasks_document


class TestTaskBoard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        (self.project_root / "planning").mkdir(parents=True)

        # 创建测试任务板
        document = {
            "tasks": [
                {
                    "id": "001",
                    "title": "测试任务1",
                    "status": "PENDING",
                    "type": "feature",
                    "priority": 1,
                    "estimated_hours": 2,
                    "dependencies": "无",
                    "sections": [
                        {
                            "heading": "验收标准",
                            "body": "运行测试: `pytest test_example.py`"
                        }
                    ]
                },
                {
                    "id": "002",
                    "title": "测试任务2",
                    "status": "PENDING",
                    "type": "test",
                    "priority": 2,
                    "estimated_hours": 1,
                    "dependencies": "#001",
                    "sections": []
                }
            ]
        }
        write_tasks_document(document, self.project_root / "planning" / "tasks.md")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_board(self):
        board = TaskBoard.load(self.project_root)
        tasks = board.get_all_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], "001")

    def test_get_next_task(self):
        board = TaskBoard.load(self.project_root)
        task = board.get_next_task()
        self.assertEqual(task["id"], "001")  # 001 无依赖，应该是下一个

    def test_get_next_task_skips_started_tasks(self):
        board = TaskBoard.load(self.project_root)
        board.update_task_status("001", "IN_PROGRESS")
        self.assertIsNone(board.get_next_task())  # 001 已开始，002 还在等它集成

    def test_update_status(self):
        board = TaskBoard.load(self.project_root)
        board.update_task_status("001", "IN_PROGRESS")

        task = board.get_task("001")
        self.assertEqual(task["status"], "IN_PROGRESS")

    def test_get_acceptance_commands(self):
        board = TaskBoard.load(self.project_root)
        commands = board.get_acceptance_commands("001")
        self.assertEqual(len(commands), 1)
        self.assertIn("pytest", commands[0])

    def test_build_context(self):
        board = TaskBoard.load(self.project_root)
        task = board.get_task("001")
        context = board.build_context(task)

        self.assertIn("任务 001", context)
        self.assertIn("测试任务1", context)
        self.assertIn("验收标准", context)


class TestExecutionConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config(self):
        config = ExecutionConfig(self.project_root)
        self.assertEqual(config.get_droid_for_complexity("light"), "worker")

    def test_determine_complexity_by_execution_level(self):
        config = ExecutionConfig(self.project_root)
        task = {"execution_level": "heavy"}
        complexity = config.determine_complexity(task)
        self.assertEqual(complexity, "heavy")

    def test_determine_complexity_by_type(self):
        config = ExecutionConfig(self.project_root)
        task = {"type": "docs"}
        complexity = config.determine_complexity(task)
        self.assertEqual(complexity, "light")

    def test_determine_complexity_by_hours(self):
        config = ExecutionConfig(self.project_root)
        task = {"estimated_hours": 0.5}
        complexity = config.determine_complexity(task)
        self.assertEqual(complexity, "light")

        task = {"estimated_hours": 5}
        complexity = config.determine_complexity(task)
        self.assertEqual(complexity, "heavy")

    def test_set_droid(self):
        config = ExecutionConfig(self.project_root)
        config.set_droid_for_complexity("medium", "custom-droid")
        self.assertEqual(config.get_droid_for_complexity("medium"), "custom-droid")


class TestTaskExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        (self.project_root / "planning").mkdir(parents=True)
        (self.project_root / ".task-management").mkdir(parents=True)

        # 创建干净的默认配置
        config_file = self.project_root / ".task-management" / "config.json"
        config_file.write_text(json.dumps({
            "execution": {
                "light": "worker",
                "medium": "worker",
                "heavy": "worker"
            }
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        document = {
            "tasks": [
                {
                    "id": "001",
                    "title": "实现功能",
                    "status": "PENDING",
                    "type": "feature",
                    "priority": 1,
                    "estimated_hours": 2.5,
                    "execution_level": "normal",
                    "dependencies": "无",
                    "sections": []
                }
            ]
        }
        write_tasks_document(document, self.project_root / "planning" / "tasks.md")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_plan_execution(self):
        executor = TaskExecutor(self.project_root)
        plan = executor.plan_execution("001")

        self.assertEqual(plan["task_id"], "001")
        self.assertEqual(plan["complexity"], "medium")
        self.assertEqual(plan["droid"], "worker")
        self.assertIn("context", plan)


class TestCheckpoint(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load(self):
        checkpoint = CheckpointManager(self.project_root)
        checkpoint.save("developing", current_task="001", total=5)

        loaded = checkpoint.load()
        self.assertEqual(loaded["phase"], "developing")
        self.assertEqual(loaded["data"]["current_task"], "001")

    def test_check_no_checkpoint(self):
        checkpoint = CheckpointManager(self.project_root)
        status = checkpoint.check()
        self.assertEqual(status, "NO_CHECKPOINT")

    def test_clear(self):
        checkpoint = CheckpointManager(self.project_root)
        checkpoint.save("planning")
        checkpoint.clear()

        self.assertIsNone(checkpoint.load())


class TestExecutionHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_execution(self):
        history = ExecutionHistory(self.project_root)
        execution_id = history.record_start("001", "worker", "medium")

        self.assertTrue(execution_id.startswith("001-"))

        history.record_completion(execution_id, "success")

        records = history.get_task_history("001")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "success")


if __name__ == "__main__":
    unittest.main()
