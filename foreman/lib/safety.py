"""Native Droid sandbox settings scoped to one dispatch, never user-wide."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .workflow import protected

# Workers rate test runs and builds as medium risk, and `--auto low` stops the whole call
# when it meets one. The sandbox, not this level, is what confines those commands.
AUTONOMY = "medium"


def minimal_environment() -> dict[str, str]:
    """Keep operational variables, drop ambient API keys and tokens."""
    keys = {
        "PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "TERM",
        "FACTORY_SESSION_ID", "FACTORY_UPSTREAM_CLIENT_TYPE", "FACTORY_DEPLOYMENT_ENV",
        "FACTORY_ENV", "FACTORY_DROID_AUTO_UPDATE_ENABLED", "DROID_PROTECTED_PID",
    }
    return {key: value for key, value in os.environ.items() if key in keys}


def runtime_policy(root: Path, extra_denied: list[Path] | None = None) -> dict:
    root = root.resolve()
    home = Path.home()
    denied = [home / name for name in (
        ".factory", ".ssh", ".aws", ".azure", ".config/gcloud", ".gnupg",
        ".kube", ".docker/config.json", ".npmrc", ".pypirc", ".netrc",
    )]
    for path in home.iterdir():
        if path == root or path in root.parents or path.name in {".local", ".cache"}:
            continue
        denied.append(path)
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if protected(path.relative_to(root).as_posix()) or path.is_symlink():
                denied.append(path)
                dirs.remove(name)
            elif name in {"node_modules", ".venv", "__pycache__"}:
                dirs.remove(name)
        for name in files:
            path = Path(directory) / name
            if protected(path.relative_to(root).as_posix()) or path.is_symlink():
                denied.append(path)
    denied.extend(extra_denied or [])
    return {
        "cloudSessionSync": False,
        "sandbox": {
            "enabled": True,
            "mode": "per-command",
            "filesystem": {
                "denyRead": sorted({str(p) for p in denied}),
                "denyWrite": [str(root / p) for p in (
                    ".git", ".factory", ".task-management", "planning/tasks.json", "planning/tasks.md",
                )],
                "allowWrite": [],
            },
            "network": {"allowedDomains": []},
        },
    }


def check_capabilities(executable: str = "droid") -> dict:
    result = subprocess.run([executable, "exec", "--help"], capture_output=True, text=True, timeout=20,
                            env=minimal_environment())
    required = ["--settings", "--only-tools", "--output-format", "--model", "--auto"]
    missing = [flag for flag in required if flag not in result.stdout]
    if result.returncode or missing:
        raise ValueError("Droid 缺少必要运行参数，不能安全派发: " + ", ".join(missing))
    return {"ok": True, "flags": required,
            "scope": "仅验证 CLI 参数；沙箱必须额外通过非敏感探针验证"}


def write_policy(path: Path, policy: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
