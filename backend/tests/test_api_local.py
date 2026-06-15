from fastapi.testclient import TestClient

from app.api.routes import local as local_routes
from app.main import create_app


def test_local_directory_picker_route(monkeypatch, clean_db):
    monkeypatch.setattr(local_routes, "pick_directory", lambda *, initial_path, title: "D:/demo/project")

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/local/directories/pick",
        json={"initial_path": "D:/demo", "title": "Choose project directory"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": "D:/demo/project", "cancelled": False}


def test_local_directory_picker_cancelled(monkeypatch, clean_db):
    monkeypatch.setattr(local_routes, "pick_directory", lambda *, initial_path, title: None)

    client = TestClient(create_app())
    response = client.post("/api/v1/local/directories/pick", json={})

    assert response.status_code == 200
    assert response.json() == {"path": None, "cancelled": True}
