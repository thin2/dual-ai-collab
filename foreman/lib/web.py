"""The local web board: whether one is running for a project, and starting or stopping it."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path

from .store import atomic_write

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 5001
PORT_VARIABLE = "FOREMAN_WEB_PORT"
STATE_FILE = Path(".task-management") / "web.json"
LOG_FILE = Path(".task-management") / "web.log"
START_TIMEOUT = 15.0
RESPONSE_LIMIT = 1 << 20


def default_port() -> int:
    value = os.environ.get(PORT_VARIABLE)
    if not value:
        return DEFAULT_PORT
    if not value.isdigit() or not 0 < int(value) < 65536:
        raise ValueError(f"环境变量 {PORT_VARIABLE} 要是 1 到 65535 之间的端口号，现在是 {value!r}")
    return int(value)


def server_script() -> Path | None:
    """web_server.py: in the skill's web/ folder once installed, at the repository root in a checkout."""
    for folder in (SKILL_ROOT / "web", SKILL_ROOT.parent):
        if (folder / "web_server.py").is_file() and (folder / "web_projects.py").is_file():
            return folder / "web_server.py"
    return None


def _request(port: int, method: str, path: str, body: bytes = b"", timeout: float = 1.0) -> tuple[int, bytes]:
    """One HTTP exchange with a server on this machine: the status and the body.

    Written on a plain socket: an HTTP client would look up the address, honour proxy settings
    and load a good part of the standard library into every foreman command that only asks.
    """
    head = f"{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n"
    if body:
        head += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(("127.0.0.1", port))
        connection.sendall(head.encode("ascii") + b"\r\n" + body)
        received = b""
        while len(received) <= RESPONSE_LIMIT:
            chunk = connection.recv(65536)
            if not chunk:
                break
            received += chunk
    status, separator, content = received.partition(b"\r\n\r\n")
    words = status.split(None, 2)
    if not separator or len(words) < 2 or not words[0].startswith(b"HTTP/") or not words[1].isdigit():
        raise ValueError("not an HTTP response")
    return int(words[1]), content


def _projects(port: int, timeout: float = 1.0) -> list[dict] | None:
    """The projects the board on this port lists; None when nothing there answers like the board."""
    try:
        status, content = _request(port, "GET", "/api/projects", timeout=timeout)
        answer = json.loads(content) if status == 200 else None
    except (OSError, ValueError):
        return None
    projects = answer.get("projects") if isinstance(answer, dict) and answer.get("success") is True else None
    if not isinstance(projects, list) or not all(
        isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("path"), str)
        for item in projects
    ):
        return None
    return projects


def _entry(projects: list[dict], root: Path) -> dict | None:
    for item in projects:
        try:
            if Path(item["path"]).resolve() == root:
                return item
        except (OSError, RuntimeError):
            continue
    return None


def _address(port: int, project_id: str) -> str:
    base = f"http://localhost:{port}"
    return f"{base}/overview" if project_id == "default" else f"{base}/project/{project_id}/overview"


def _state(root: Path) -> dict | None:
    """What web start recorded for this project; None when there is no usable record."""
    try:
        state = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not all(
        isinstance(state.get(key), int) and not isinstance(state[key], bool) for key in ("pid", "port")
    ):
        return None
    return state


def board_status(root: Path) -> dict:
    """Where this project's board can be opened, if one is running. It only reads.

    A board counts when it lists this project: the one web start launched here, or one
    already running on the default port that the project was added to.
    """
    root = Path(root).resolve()
    state = _state(root)
    ports = list(dict.fromkeys([*([state["port"]] if state else []), default_port()]))
    without = None
    for port in ports:
        projects = _projects(port)
        if projects is None:
            continue
        entry = _entry(projects, root)
        if entry:
            own = bool(state) and state["port"] == port and entry["id"] == "default"
            return {"running": True, "listed": True, "port": port, "url": _address(port, entry["id"]),
                    "pid": state["pid"] if own else None}
        without = without or port
    return {"running": without is not None, "listed": False, "port": without, "url": None, "pid": None}


def _free_port(first: int) -> int:
    for port in range(first, min(first + 20, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise ValueError(f"端口 {first} 到 {first + 19} 都被占用；用 --port 指定一个空闲端口")


def _add_to(port: int, root: Path) -> str:
    """List this project on a board that is already running; return the project's id there."""
    body = json.dumps({"name": root.name, "path": str(root)}).encode("utf-8")
    try:
        status, content = _request(port, "POST", "/api/projects", body, timeout=5.0)
        answer = json.loads(content)
        if status != 201:
            raise ValueError(answer.get("error") if isinstance(answer, dict) else f"HTTP {status}")
        return answer["project"]["id"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"端口 {port} 上的看板没能登记这个项目（{error}）；"
                         "在看板页面顶部手工登记，或用 --port 另起一个") from error


def start_board(root: Path, port: int | None = None) -> dict:
    """Make sure a board shows this project: reuse one that is running, otherwise start one in the background."""
    root = Path(root).resolve()
    status = board_status(root)
    if status["listed"]:
        return {**status, "action": "running"}
    if status["running"] and port is None:
        return {"running": True, "listed": True, "port": status["port"], "pid": None, "action": "added",
                "url": _address(status["port"], _add_to(status["port"], root))}
    script = server_script()
    if script is None:
        raise ValueError(f"这份安装里没有 Web 看板的文件（{SKILL_ROOT / 'web' / 'web_server.py'}）："
                         "用源码仓库的 install.py 重新安装技能")
    if find_spec("flask") is None:
        raise ValueError(f"Web 看板需要 Flask，而 {sys.executable} 里没有装："
                         f"运行 {sys.executable} -m pip install --user Flask 后重试")
    if port is None:
        port = _free_port(default_port())
    elif _free_port(port) != port:
        raise ValueError(f"端口 {port} 被占用；换一个端口，或不带 --port 让它自己找")
    log = root / LOG_FILE
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as output:
        # Its own session, so it outlives this command and the terminal that ran it.
        process = subprocess.Popen([sys.executable, str(script), str(port), "--project", str(root), "--quiet"],
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                   start_new_session=True, cwd=root)
    deadline = time.monotonic() + START_TIMEOUT
    while _entry(_projects(port, 0.5) or [], root) is None:
        if process.poll() is not None or time.monotonic() > deadline:
            if process.poll() is None:
                process.kill()
            process.wait()
            tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:])
            raise ValueError(f"看板没能启动；日志在 {log}，最后几行：\n{tail}")
        time.sleep(0.2)
    atomic_write(root / STATE_FILE, json.dumps({
        "pid": process.pid, "port": port, "started_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    return {"running": True, "listed": True, "port": port, "url": _address(port, "default"),
            "pid": process.pid, "action": "started", "log": str(log)}


def _is_board(pid: int) -> bool:
    """Whether this PID still belongs to a board; a PID is handed out again after its process exits."""
    try:
        listed = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
    except OSError:
        return False
    return listed.returncode == 0 and "web_server.py" in listed.stdout


def stop_board(root: Path) -> dict:
    """Stop the board web start launched for this project. A board started any other way is left alone."""
    root = Path(root).resolve()
    state = _state(root)
    if state is None:
        return {"stopped": False, "port": None}
    pid, port = state["pid"], state["port"]
    stopped = False
    if _is_board(pid):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except OSError:
            pass
        deadline = time.monotonic() + 5.0
        while stopped and _is_board(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
    (root / STATE_FILE).unlink()
    return {"stopped": stopped, "port": port}
