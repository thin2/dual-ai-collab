from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def run_installer(self, tmp, *extra):
        bin_dir = Path(tmp) / "bin"
        return subprocess.run(
            [sys.executable, str(ROOT / "install.py"), "--source", str(ROOT), "--target", str(Path(tmp) / "skill"),
             "--bin-dir", str(bin_dir), *extra],
            capture_output=True, text=True,
            env={**os.environ, "HOME": tmp, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})

    def test_bin_dir_links_a_foreman_command_that_works_in_any_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = str(Path(tmp).resolve())
            link = Path(tmp) / "bin" / "foreman"
            project = Path(tmp) / "project"
            project.mkdir()
            installed = self.run_installer(tmp)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertIn("command: foreman\n", installed.stdout)
            self.assertIn(f"link: {link} -> {Path(tmp) / 'skill' / 'bin' / 'foreman'}", installed.stdout)
            shown = subprocess.run([str(link), "--help"], cwd=project, capture_output=True, text=True)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertTrue(shown.stdout.startswith("usage: foreman "), shown.stdout)
            self.assertEqual(subprocess.run([str(link), "init"], cwd=project, capture_output=True).returncode, 0)
            self.assertTrue((project / "planning" / "tasks.json").exists())
            self.assertFalse((Path(tmp) / "skill" / "planning").exists())
            # Installing again replaces the link this installer made.
            self.assertEqual(self.run_installer(tmp, "--force").returncode, 0)
            self.assertTrue(link.is_symlink())

    def test_bin_dir_never_replaces_another_program_called_foreman(self):
        for other in ("file", "link"):
            with self.subTest(other=other), tempfile.TemporaryDirectory() as tmp:
                link = Path(tmp) / "bin" / "foreman"
                link.parent.mkdir()
                program = Path(tmp) / "procfile-runner"
                program.write_text("#!/bin/sh\n", encoding="utf-8")
                if other == "file":
                    link.write_text("#!/bin/sh\n", encoding="utf-8")
                else:
                    link.symlink_to(program)
                refused = self.run_installer(tmp)
                self.assertEqual(refused.returncode, 1)
                self.assertIn("不是 foreman 技能的链接", refused.stderr)
                self.assertEqual(link.read_text(encoding="utf-8"), "#!/bin/sh\n")
                self.assertEqual(link.is_symlink(), other == "link")
                self.assertFalse((Path(tmp) / "skill").exists())  # Refused before anything was copied.

    def test_bin_dir_replaces_a_link_left_by_a_removed_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "bin" / "foreman"
            link.parent.mkdir()
            link.symlink_to(Path(tmp) / "removed-skill" / "bin" / "foreman")
            self.assertEqual(self.run_installer(tmp).returncode, 0)
            self.assertEqual(link.resolve(), (Path(tmp) / "skill" / "bin" / "foreman").resolve())

    def test_bin_dir_is_only_for_the_foreman_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_installer(tmp, "--profile", "full").returncode, 2)
            self.assertFalse((Path(tmp) / "skill").exists())

    def release(self, tmp, files):
        """A repository root whose foreman/ holds exactly these files: one version of the skill."""
        skill = Path(tmp) / "source" / "foreman"
        if skill.exists():
            shutil.rmtree(skill)
        for name, content in {"SKILL.md": "---\nname: foreman\n---\n", "bin/foreman": "#!/bin/sh\n", **files}.items():
            (skill / name).parent.mkdir(parents=True, exist_ok=True)
            (skill / name).write_text(content, encoding="utf-8")
        return skill.parent

    def test_upgrade_removes_what_the_previous_version_installed_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skill"
            source = self.release(tmp, {"lib/kept.py": "", "lib/dropped.py": "", "references/dropped.md": "old",
                                        "tools/only.py": ""})
            self.assertEqual(install.install(target, source, force=False, profile="foreman"), [])
            # The installed copy has been run, and its owner keeps files of their own in it.
            for module in ("lib/kept", "lib/dropped", "tools/only"):
                folder, stem = module.split("/")
                (target / folder / "__pycache__").mkdir(exist_ok=True)
                (target / folder / "__pycache__" / f"{stem}.cpython-39.pyc").write_bytes(b"")
            (target / "notes.md").write_text("mine", encoding="utf-8")
            (target / "lib" / "mine.py").write_text("mine", encoding="utf-8")

            self.release(tmp, {"lib/kept.py": "", "docs/added.md": "new"})
            notes = install.install(target, source, force=True, profile="foreman")
            self.assertEqual(len(notes), 1)
            self.assertTrue(notes[0].startswith("removed: lib/dropped.py、references/dropped.md、tools/only.py（"))
            self.assertFalse((target / "lib" / "dropped.py").exists())
            self.assertFalse((target / "lib" / "__pycache__" / "dropped.cpython-39.pyc").exists())
            self.assertTrue((target / "lib" / "__pycache__" / "kept.cpython-39.pyc").exists())
            # A folder goes once nothing is left in it, whether it held a document or a module that had been run.
            self.assertFalse((target / "references").exists())
            self.assertFalse((target / "tools").exists())
            self.assertEqual((target / "docs" / "added.md").read_text(encoding="utf-8"), "new")
            self.assertEqual((target / "notes.md").read_text(encoding="utf-8"), "mine")
            self.assertEqual((target / "lib" / "mine.py").read_text(encoding="utf-8"), "mine")
            self.assertEqual(install.install(target, source, force=True, profile="foreman"), [])

    def test_install_over_one_that_left_no_record_deletes_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skill"
            source = self.release(tmp, {"lib/old.py": ""})
            install.install(target, source, force=False, profile="foreman")
            (target / install.MANIFEST).unlink()  # as installed by a version that kept no record
            self.release(tmp, {"lib/new.py": ""})
            notes = install.install(target, source, force=True, profile="foreman")
            self.assertEqual(len(notes), 1)
            self.assertIn("没有留下文件清单", notes[0])
            self.assertTrue((target / "lib" / "old.py").exists())
            # From here on there is a record, so the next upgrade cleans up after this one.
            self.release(tmp, {})
            self.assertTrue(install.install(target, source, force=True, profile="foreman")[0].startswith(
                "removed: lib/new.py（"))
            self.assertTrue((target / "lib" / "old.py").exists())

    def test_damaged_record_cannot_delete_outside_the_skill_or_a_file_this_version_ships(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skill"
            source = self.release(tmp, {"lib/kept.py": ""})
            install.install(target, source, force=False, profile="foreman")
            outside = Path(tmp) / "outside.txt"
            outside.write_text("not the skill's", encoding="utf-8")
            for record in ({"files": ["../outside.txt", str(outside), "lib/../SKILL.md", "lib", ""]},
                           {"files": "lib/kept.py"}, ["lib/kept.py"], None):
                with self.subTest(record=record):
                    content = "{" if record is None else json.dumps(record)
                    (target / install.MANIFEST).write_text(content, encoding="utf-8")
                    notes = install.install(target, source, force=True, profile="foreman")
                    self.assertFalse(any(note.startswith("removed:") for note in notes), notes)
                    self.assertTrue(outside.exists())
                    self.assertTrue((target / "SKILL.md").exists() and (target / "lib" / "kept.py").exists())

    def test_renaming_a_file_only_by_case_keeps_the_new_one(self):
        # On macOS both names are one file: removing the old name would delete what was just installed.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skill"
            source = self.release(tmp, {"references/Guide.md": "old"})
            install.install(target, source, force=False, profile="foreman")
            self.release(tmp, {"references/guide.md": "new"})
            install.install(target, source, force=True, profile="foreman")
            self.assertEqual((target / "references" / "guide.md").read_text(encoding="utf-8"), "new")

    def test_record_lists_exactly_the_files_of_the_installed_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skill"
            for extra in ((), ("--force",)):
                installed = self.run_installer(tmp, *extra)
                self.assertEqual(installed.returncode, 0, installed.stderr)
                self.assertNotIn("removed:", installed.stdout)
                self.assertNotIn("文件清单", installed.stdout)
                # Running the installed command leaves compiled files, which are not part of the skill.
                subprocess.run([str(target / "bin" / "foreman"), "--version"], capture_output=True, check=True)
            recorded = json.loads((target / install.MANIFEST).read_text(encoding="utf-8"))["files"]
            present = {path.relative_to(target).as_posix() for path in target.rglob("*")
                       if path.is_file() and "__pycache__" not in path.parts and path.name != install.MANIFEST}
            self.assertEqual(set(recorded), present)
            self.assertIn("SKILL.md", recorded)
            self.assertIn("bin/foreman", recorded)

    def test_installer_says_what_to_type_when_foreman_is_not_on_path(self):
        launcher = Path("/skills/foreman/bin/foreman")
        with patch("install.shutil.which", return_value=None):
            notes = install.launcher_notes(launcher, None)
            self.assertEqual(notes[0], f"command: {launcher}")
            self.assertIn("--bin-dir", notes[-1])
            self.assertIn("/elsewhere 不在 PATH 里", install.launcher_notes(launcher, Path("/elsewhere/foreman"))[-1])
        with patch("install.shutil.which", return_value="/usr/local/bin/foreman"):
            notes = install.launcher_notes(launcher, None)
            self.assertEqual(notes[0], f"command: {launcher}")
            self.assertIn("另一个程序（/usr/local/bin/foreman）", notes[-1])


if __name__ == "__main__":
    unittest.main()
