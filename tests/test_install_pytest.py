from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import install  # noqa: E402


class InstallTests(unittest.TestCase):
    def test_installed_skill_plans_and_executes_in_target_project_without_model_cli(self):
        """The one merged skill covers what the planning-only skill did, from its installed copy."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            project = Path(tmp) / "project"
            project.mkdir()
            install.install(target, ROOT, force=False, profile="foreman")
            self.assertTrue((target / "SKILL.md").exists())
            self.assertFalse((target / "source.json").exists())
            tool = [sys.executable, str(target / "tools" / "cli.py")]
            def run(*args):
                # No droid on PATH: planning and direct execution must not need it.
                return subprocess.run(tool + list(args), cwd=project, capture_output=True, text=True,
                                      env={"PATH": "/usr/bin:/bin", "HOME": tmp})
            self.assertEqual(run("init").returncode, 0)
            plan = project / "planning" / "plan.json"
            plan.write_text(json.dumps({
                "id": "001", "title": "写说明", "description": "补一份说明文档",
                "files": ["docs/guide.md"], "runtime_dependencies": ["docs"],
                "acceptance": [{"id": "exists", "scenario": "查看文档", "expected": "文件存在且非空",
                                "method": "command", "command": "test -s docs/guide.md"}],
            }), encoding="utf-8")
            self.assertEqual(run("add", "--file", str(plan)).returncode, 0)
            self.assertTrue((project / "planning" / "tasks.json").exists())
            self.assertTrue((project / "planning" / "tasks.md").exists())
            checked = run("validate")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(json.loads(run("show", "--json").stdout)[0]["id"], "001")
            self.assertIn("补一份说明文档", run("show", "001").stdout)
            started = run("execution", "begin", "001")
            self.assertEqual(started.returncode, 0, started.stderr)
            execution_id = json.loads(started.stdout)["execution_id"]
            (project / "docs").mkdir()
            (project / "docs" / "guide.md").write_text("说明\n", encoding="utf-8")
            self.assertEqual(run("execution", "finish", execution_id, "--outcome", "completed").returncode, 0)
            self.assertEqual(json.loads(run("execution", "inspect", execution_id).stdout)["added"], ["docs/guide.md"])
            proof = project / "planning" / "acceptance-001.json"
            proof.write_text(json.dumps({
                "inspection": "只新增了 docs/guide.md",
                "checks": [{"id": "exists", "status": "passed", "evidence": "test -s docs/guide.md 退出码 0"}],
            }), encoding="utf-8")
            accepted = run("execution", "accept", execution_id, "--evidence-file", str(proof))
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("AWAITING_INTEGRATION", run("show").stdout)
            self.assertIn("total_tasks: 1", run("checkpoint", "check").stdout)
            self.assertNotEqual(run("run", "001", "--dispatcher", "custom:none").returncode, 0)
            self.assertFalse((target / "planning").exists())
            self.assertFalse((target / ".task-management").exists())

    def test_planning_profile_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            install.install(Path(tmp) / "x", ROOT, force=False, profile="planning")

    def test_install_copies_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            install.install(target, ROOT, force=False)

            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue((target / "scripts" / "cli.py").exists())
            self.assertTrue((target / "references" / "interview.md").exists())

    def test_install_requires_force_for_non_empty_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            target.mkdir(parents=True)
            (target / "existing.txt").write_text("existing", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                install.install(target, ROOT, force=False)

            install.install(target, ROOT, force=True)
            self.assertTrue((target / "SKILL.md").exists())

    def test_install_skips_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            install.install(target, ROOT, force=False)

            pycache_files = list((target / "scripts").rglob("__pycache__"))
            self.assertEqual(len(pycache_files), 0)


if __name__ == "__main__":
    unittest.main()
