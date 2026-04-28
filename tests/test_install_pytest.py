from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import install  # noqa: E402


class InstallTests(unittest.TestCase):
    def test_install_copies_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            install.install(target, ROOT, force=False)

            self.assertTrue((target / "dual-ai-collab.md").exists())
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
            self.assertTrue((target / "dual-ai-collab.md").exists())

    def test_install_skips_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "installed-skill"
            install.install(target, ROOT, force=False)

            pycache_files = list((target / "scripts").rglob("__pycache__"))
            self.assertEqual(len(pycache_files), 0)


if __name__ == "__main__":
    unittest.main()
