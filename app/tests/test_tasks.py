import pytest
from fastapi.testclient import TestClient

import storage
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_storage():
    storage.init_db() 
    storage.reset()


def test_list_is_empty_at_start():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


def test_create_then_list():
    created = client.post("/tasks", json={"title": "Réviser DevOps"})
    assert created.status_code == 201
    assert created.json()["title"] == "Réviser DevOps"

    listed = client.get("/tasks")
    assert len(listed.json()) == 1


def test_create_with_empty_title_is_rejected():
    response = client.post("/tasks", json={"title": ""})
    assert response.status_code == 422


def test_delete_task():
    task_id = client.post("/tasks", json={"title": "À supprimer"}).json()["id"]
    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.get(f"/tasks/{task_id}").status_code == 404


def test_delete_unknown_task_returns_404():
    assert client.delete("/tasks/999").status_code == 404