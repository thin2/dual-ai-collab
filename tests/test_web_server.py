"""HTTP contracts and persistence integration for the Flask service."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_server import create_app


@pytest.fixture
def client(tmp_path):
    planning = tmp_path / "planning"
    planning.mkdir()
    (planning / "tasks.json").write_text(json.dumps({"tasks": [
        {"id": "001", "title": "测试任务", "status": "OPEN"},
        {"id": "002", "title": "Finished", "status": "DONE"},
    ]}), encoding="utf-8")
    app = create_app(tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def test_read_and_update(client):
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert len(response.json["tasks"]) == 2
    assert client.get("/api/tasks/1").json["task"]["title"] == "测试任务"
    assert client.put("/api/tasks/001", json={"status": "IN_PROGRESS"}).status_code == 200
    assert client.get("/api/tasks/001").json["task"]["status"] == "IN_PROGRESS"
    task_file = Path(client.application.config["TASK_FILE"])
    assert json.loads(task_file.read_text())["tasks"][0]["status"] == "IN_PROGRESS"
    assert "IN_PROGRESS" in task_file.with_name("codex-tasks.md").read_text()


@pytest.mark.parametrize("payload", [{}, {"status": "bogus"}, {"status": []}, [], None])
def test_invalid_body(client, payload):
    response = client.put("/api/tasks/001", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert response.json["success"] is False
    assert client.get("/api/tasks/001").json["task"]["status"] == "OPEN"


@pytest.mark.parametrize("method,url,kwargs,code", [
    ("get", "/api/tasks/999", {}, 404),
    ("put", "/api/tasks/999", {"json": {"status": "DONE"}}, 404),
    ("get", "/api/unknown", {}, 404),
    ("post", "/api/tasks", {}, 405),
    ("put", "/api/tasks/001", {"data": "{" , "content_type": "application/json"}, 400),
    ("put", "/api/tasks/001", {"data": "text", "content_type": "text/plain"}, 415),
])
def test_http_errors(client, method, url, kwargs, code):
    response = getattr(client, method)(url, **kwargs)
    assert response.status_code == code
    assert response.json["success"] is False


def test_board(client):
    stats = client.get("/api/board").json["stats"]
    assert stats["total"] == 2
    assert stats["by_status"]["OPEN"] == 1
    assert stats["completed"] == 0
    assert stats["completion_rate"] == 0.0


def test_empty_board(client):
    Path(client.application.config["TASK_FILE"]).write_text('{"tasks": []}')
    assert client.get("/api/board").json["stats"]["completion_rate"] == 0


def test_history(client):
    assert client.get("/api/history").json["history"] == []
    directory = Path(client.application.config["HISTORY_DIR"])
    directory.mkdir(parents=True)
    for name, date in [("001", "2026-10-08"), ("002", "2026-10-07")]:
        (directory / f"{name}.json").write_text(json.dumps({"task_num": name, "start_time": date}))
    response = client.get("/api/history")
    assert response.status_code == 200
    assert [record["task_num"] for record in response.json["history"]] == ["001", "002"]
    (directory / "broken.json").write_text("{")
    assert client.get("/api/history").status_code == 500


def test_storage_failure(client):
    Path(client.application.config["TASK_FILE"]).write_text("{")
    response = client.get("/api/tasks")
    assert response.status_code == 500
    assert response.json == {"success": False, "error": "Internal server error"}
