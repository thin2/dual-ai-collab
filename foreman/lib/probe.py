"""Fail-closed sandbox probe using only disposable, non-sensitive fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .safety import (
    AUTONOMY,
    check_capabilities,
    minimal_environment,
    runtime_policy,
    write_policy,
)
from .team import list_byok_models


def fingerprint(executable: str) -> str:
    path = Path(shutil.which(executable) or executable).resolve()
    stat = path.stat()
    return hashlib.sha256(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()


def policy_fingerprint(root: Path) -> str:
    return hashlib.sha256(json.dumps(runtime_policy(root), sort_keys=True).encode()).hexdigest()


def verify_receipt(root: Path, dispatcher: str, executable: str):
    path = root / ".task-management" / "sandbox-probe.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("先运行 foreman preflight --dispatcher <用户选定 ID> 验证沙箱") from exc
    if not (data.get("ok") and data.get("dispatcher") == dispatcher
            and data.get("autonomy") == AUTONOMY
            and data.get("executable") == fingerprint(executable)
            and data.get("policy") == policy_fingerprint(root)):
        raise ValueError("沙箱探针未通过或环境已变化，必须重新运行 foreman preflight --dispatcher <用户选定 ID>")


def run_probe(root: Path, dispatcher: str, executable: str = "droid",
              settings_path: Path | None = None, timeout: int = 120) -> dict:
    if dispatcher not in {m["id"] for m in list_byok_models(settings_path)}:
        raise ValueError(f"探针模型 {dispatcher} 不在已配置的模型里：必须是用户选定的完整 BYOK ID，"
                         "即 foreman models 的第一列")
    check_capabilities(executable)
    root = root.resolve()
    state = root / ".task-management"
    state.mkdir(exist_ok=True)
    receipt = state / "sandbox-probe.json"
    # Remove only our previous approval before trying again.
    receipt.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="tm-probe-", dir=root) as tmp:
        directory = Path(tmp)
        allowed = directory / "allowed.txt"
        denied = directory / "denied.txt"
        output = directory / "result.json"
        hook_seen = directory / "hook-seen"
        allowed.write_text("public fixture", encoding="utf-8")
        denied.write_text("non-sensitive blocked fixture", encoding="utf-8")
        script = directory / "probe.py"
        script.write_text(
            "import json, pathlib\n"
            f"allowed=pathlib.Path({str(allowed)!r})\n"
            f"denied=pathlib.Path({str(denied)!r})\n"
            "result={'allowed_read':allowed.read_text()=='public fixture'}\n"
            "try:\n denied.read_text(); result['denied_read']=False\n"
            "except PermissionError:\n result['denied_read']=True\n"
            "try:\n denied.write_text('unexpected'); result['denied_write']=False\n"
            "except PermissionError:\n result['denied_write']=True\n"
            f"pathlib.Path({str(output)!r}).write_text(json.dumps(result))\n"
            "print('PROBE_FINISHED')\n", encoding="utf-8",
        )
        command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
        hook = directory / "guard.py"
        hook.write_text(
            "import json,sys,pathlib\n"
            "event=json.load(sys.stdin)\n"
            "args=event.get('tool_input',{})\n"
            f"ok=event.get('tool_name')=='Execute' and args.get('command')=={command!r}\n"
            # Workers label test runs medium; the probe has to show such a call is let through.
            f"ok=ok and 'cwd' not in args and bool(args.get('summary')) and args.get('riskLevel')=={AUTONOMY!r}\n"
            "if not ok:\n print('Probe accepts only its exact fixture command',file=sys.stderr); sys.exit(2)\n"
            f"pathlib.Path({str(hook_seen)!r}).write_text('seen')\n", encoding="utf-8",
        )
        policy = runtime_policy(root, [denied])
        policy["sandbox"]["filesystem"]["denyWrite"].append(str(denied))
        policy["hooks"] = {"PreToolUse": [{
            "matcher": "*", "hooks": [{"type": "command", "command":
                f"{shlex.quote(sys.executable)} {shlex.quote(str(hook))}", "timeout": 10}],
        }]}
        policy_file = directory / "runtime.json"
        write_policy(policy_file, policy)
        prompt = (
            "Run exactly one Execute tool call, then stop. Do not inspect any other files."
            " This harmless local probe reads two dummy fixtures and records kernel permission outcomes."
            " Keep riskLevel exactly as given: the probe also checks that calls at this level are permitted."
            "\nUse this exact JSON: " + json.dumps({
                "command": command, "riskLevel": AUTONOMY, "summary": "Check disposable sandbox fixtures",
            })
        )
        process = subprocess.Popen(
            [executable, "exec", "--model", dispatcher, "--only-tools", "Execute",
             "--settings", str(policy_file), "--output-format", "json", "--auto", AUTONOMY, prompt],
            cwd=root, env=minimal_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = -1
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result = {}
        hook_applied = hook_seen.exists()
        ok = (code == 0 and hook_applied and
              all(result.get(key) is True for key in ("allowed_read", "denied_read", "denied_write")))
    data = {"ok": ok, "checks": result, "hook_applied": hook_applied, "autonomy": AUTONOMY,
            "dispatcher": dispatcher, "executable": fingerprint(executable),
            "policy": policy_fingerprint(root)}
    if ok:
        write_policy(receipt, data)
    return data
