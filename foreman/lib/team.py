#!/usr/bin/env python3
"""固定模型子 Agent 团队：列出 BYOK 模型、生成项目级 droid、派发前检查、核对实际模型。"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

try:
    from .config import ExecutionConfig
except ImportError:
    from config import ExecutionConfig

DROID_PREFIX = "tm-"
MANAGED_MARKER = "<!-- managed-by: task-management -->"
ROLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DEFAULT_SETTINGS = Path.home() / ".factory" / "settings.json"
DEFAULT_SESSIONS = Path.home() / ".factory" / "sessions"

DEFAULT_RULES = """规则：
- 只修改任务中列出的文件；需要改动其他文件时，停止并报告。
- 不要读取或输出任何密钥、令牌或凭据文件（例如 ~/.factory/settings.json、.env）。
- 不要提交、推送或部署。
- 结束时报告修改过的文件、运行过的验证命令及其结果。
- 任务不清楚或被阻塞时，停止并说明原因，不要猜测。"""


class TeamError(Exception):
    """团队配置错误"""


def droid_name(role: str) -> str:
    return DROID_PREFIX + role


def _droid_path(project_root: Path, role: str) -> Path:
    return Path(project_root) / ".factory" / "droids" / f"{droid_name(role)}.md"


def _endpoint(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url or "")
    if not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return parsed.hostname, port or (443 if parsed.scheme == "https" else 80)


def _load_custom_models(settings_path: Path | None) -> list[dict]:
    path = Path(settings_path or DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TeamError(f"无法读取模型配置 {path}: {exc}") from exc
    entries = []
    for entry in data.get("customModels") or []:
        if isinstance(entry, dict) and entry.get("model"):
            entries.append(entry)
    return entries


def _model_id(entry: dict) -> str:
    return entry.get("id") or f"custom:{entry['model']}"


def list_byok_models(settings_path: Path | None = None) -> list[dict]:
    """列出用户自己配置的模型。只返回标识和服务地址的主机端口，不返回密钥。"""
    models = []
    for entry in _load_custom_models(settings_path):
        endpoint = _endpoint(entry.get("baseUrl", ""))
        models.append({
            "id": _model_id(entry),
            "name": entry.get("displayName") or entry["model"],
            "provider": entry.get("provider", ""),
            "endpoint": f"{endpoint[0]}:{endpoint[1]}" if endpoint else "",
        })
    return models


def model_catalog(settings_path: Path | None = None, query: str = "", recommended: list[str] | None = None) -> dict:
    """推荐只调整排序；同名模型按完整 ID 保留，搜索不改变总列表。"""
    models = list_byok_models(settings_path)
    preferred = recommended or []
    unknown = set(preferred) - {m["id"] for m in models}
    if unknown:
        raise TeamError("推荐模型 ID 不存在: " + ", ".join(sorted(unknown)))
    for model in models:
        model["recommended"] = model["id"] in preferred
        # ID 是线路的可靠标识，不从展示名猜测代理层级。
        model["route"] = model["id"]
    models.sort(key=lambda m: (not m["recommended"], preferred.index(m["id"]) if m["recommended"] else 0))
    visible = [m for m in models if query.casefold() in " ".join(
        str(m[k]) for k in ("id", "name", "provider", "endpoint")
    ).casefold()]
    return {"total": len(models), "matches": len(visible), "models": visible,
            "selection": "完整 ID 精确选择；推荐不限制选择；无匹配时清除搜索或直接输入 ID"}


def _yaml_text(value: str) -> str:
    value = " ".join(value.split())
    if re.search(r":\s|\s#|^[\s\-?:,\[\]{}#&*!|>'\"%@`]", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def render_droid(role: str, model: str, description: str, instructions: str | None, read_only: bool) -> str:
    lines = [
        "---",
        f"name: {droid_name(role)}",
        f"description: {_yaml_text(description)}",
        f"model: {model}",
    ]
    if read_only:
        lines.append("tools: read-only")
    lines.append("---")
    body = (instructions or f"你负责本项目中的「{role}」任务：{' '.join(description.split())}").strip()
    return "\n".join(lines) + f"\n\n{body}\n\n{DEFAULT_RULES}\n\n{MANAGED_MARKER}\n"


def _read_droid_model(path: Path) -> str | None:
    match = re.search(r"^model:\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def configure_role(
    project_root: Path,
    role: str,
    model: str,
    description: str,
    instructions: str | None = None,
    read_only: bool = False,
    force: bool = False,
    settings_path: Path | None = None,
) -> Path:
    """为角色生成固定模型的项目级 droid，并写入项目配置。"""
    if not ROLE_PATTERN.match(role or ""):
        raise TeamError(f"角色名无效: {role}（只能用小写字母、数字和连字符，且不能以连字符开头）")
    if not description or not description.strip():
        raise TeamError("角色描述不能为空")
    known = {m["id"] for m in list_byok_models(settings_path)}
    if model not in known:
        raise TeamError(f"模型不在 BYOK 列表中: {model}。先运行 models 查看可用的模型 ID")

    path = _droid_path(project_root, role)
    if path.exists() and MANAGED_MARKER not in path.read_text(encoding="utf-8") and not force:
        raise TeamError(f"{path} 已存在且不是本技能生成的；确认可以覆盖后加 --force")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_droid(role, model, description, instructions, read_only), encoding="utf-8")

    ExecutionConfig(Path(project_root)).set_role(role, {
        "droid": droid_name(role),
        "model": model,
        "description": " ".join(description.split()),
        "read_only": read_only,
    })
    return path


def remove_role(project_root: Path, role: str) -> bool:
    removed = ExecutionConfig(Path(project_root)).remove_role(role)
    path = _droid_path(project_root, role)
    if path.exists() and MANAGED_MARKER in path.read_text(encoding="utf-8"):
        path.unlink()
        removed = True
    return removed


def _reachable(endpoint: tuple[str, int], timeout: float) -> bool:
    try:
        with socket.create_connection(endpoint, timeout=timeout):
            return True
    except OSError:
        return False


def check_team(project_root: Path, settings_path: Path | None = None, timeout: float = 3.0) -> list[dict]:
    """派发前检查每个角色：droid 文件、模型是否仍在 BYOK 列表、模型服务是否能连通。"""
    roles = ExecutionConfig(Path(project_root)).get_roles()
    endpoints = {_model_id(e): _endpoint(e.get("baseUrl", "")) for e in _load_custom_models(settings_path)}
    results = []
    for role, entry in sorted(roles.items()):
        problems = []
        model = entry.get("model", "")
        path = _droid_path(project_root, role)
        if not path.exists():
            problems.append(f"缺少 droid 文件 {path}")
        elif _read_droid_model(path) != model:
            problems.append(f"droid 文件中的模型 {_read_droid_model(path)} 与配置 {model} 不一致")
        if model not in endpoints:
            problems.append(f"模型 {model} 已不在 BYOK 列表中")
        elif endpoints[model] and not _reachable(endpoints[model], timeout):
            host, port = endpoints[model]
            problems.append(f"无法连接模型服务 {host}:{port}（代理或服务可能没有运行）")
        results.append({
            "role": role,
            "droid": entry.get("droid", droid_name(role)),
            "model": model,
            "ok": not problems,
            "problems": problems,
        })
    return results


def _last_turn_outcome(path: Path) -> str | None:
    """How the session's last turn ended (completed, permission_rejected, ...); None when not recorded."""
    reason = None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if '"agent_turn_outcome"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") == "agent_turn_outcome":
                    reason = event.get("reason")
    except OSError:
        return None
    return reason if isinstance(reason, str) else None


def audit_runs(project_root: Path, sessions_dir: Path | None = None, limit: int = 20,
               execution_id: str | None = None) -> list[dict]:
    """从 Droid 本地会话记录核对子 Agent 实际使用的模型。

    依赖 Droid 1.6 的本地记录格式：子 Agent 会话的标题以 "<droid 名>: <description>" 开头，
    同名 .settings.json 中的 model 是实际使用的模型。格式变化时返回空列表，不报错。
    """
    roles = ExecutionConfig(Path(project_root)).get_roles()
    expected = {entry["droid"]: (role, entry["model"]) for role, entry in roles.items() if entry.get("droid")}
    base = Path(sessions_dir or DEFAULT_SESSIONS) / str(Path(project_root).resolve()).replace("/", "-")
    if not expected or not base.is_dir():
        return []

    records = []
    for path in sorted(base.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with path.open(encoding="utf-8") as handle:
                first = json.loads(handle.readline())
        except (OSError, json.JSONDecodeError):
            continue
        if not first.get("callingSessionId"):
            continue
        title = str(first.get("title", ""))
        if execution_id and f"[tm:{execution_id}]" not in title:
            continue
        droid = title.split(":", 1)[0].strip().lower()
        if droid not in expected:
            continue
        try:
            settings = json.loads(path.with_name(f"{path.stem}.settings.json").read_text(encoding="utf-8"))
            actual = settings.get("model")
        except (OSError, json.JSONDecodeError):
            actual = None
        role, model = expected[droid]
        records.append({
            "session_id": first.get("id", path.stem),
            "title": title,
            "role": role,
            "expected": model,
            "actual": actual,
            "ok": actual == model,
            "outcome": _last_turn_outcome(path),
        })
        if len(records) >= limit:
            break
    return records
