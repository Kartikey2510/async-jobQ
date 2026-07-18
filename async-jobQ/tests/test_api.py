"""API-layer integration tests (FastAPI TestClient)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


@pytest.fixture
def client(SessionLocal):
    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch("app.main.init_db"),
            patch("app.main.worker_pool") as mock_pool,
            patch("app.services.jobs.worker_pool.enqueue") as mock_enqueue,
        ):
            mock_pool.start = MagicMock()
            mock_pool.stop = MagicMock()
            with TestClient(app) as test_client:
                yield test_client, mock_enqueue
    finally:
        app.dependency_overrides.clear()


def test_create_and_get_job(client):
    test_client, mock_enqueue = client

    create = test_client.post("/jobs", json={"prompt": "Say hello"})
    assert create.status_code == 202
    job_id = create.json()["id"]
    assert job_id
    mock_enqueue.assert_called_once_with(job_id)

    fetch = test_client.get(f"/jobs/{job_id}")
    assert fetch.status_code == 200
    body = fetch.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["result"] is None


def test_get_job_not_found(client):
    test_client, _ = client
    resp = test_client.get("/jobs/does-not-exist")
    assert resp.status_code == 404


def test_create_job_rejects_empty_payload(client):
    test_client, mock_enqueue = client
    resp = test_client.post("/jobs", json={})
    assert resp.status_code == 422
    mock_enqueue.assert_not_called()
