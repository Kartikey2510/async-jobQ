"""Unit tests for WorkerPool job processing logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.job import JobStatus
from app.workers.errors import PayloadValidationError, ProviderAuthError
from app.workers.pool import WorkerPool


@pytest.fixture
def pool(SessionLocal, monkeypatch):
    monkeypatch.setattr("app.workers.pool.SessionLocal", SessionLocal)
    return WorkerPool(num_workers=1)


def test_process_job_success(pool, db, store, queued_job, SessionLocal):
    fake_result = {
        "provider": "digitalocean",
        "model": "llama3.3-70b-instruct",
        "content": "Hello!",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    with patch("app.workers.pool.run_inference", return_value=fake_result) as mock_infer:
        pool._process_job(queued_job.id)

    mock_infer.assert_called_once_with({"prompt": "Say hello"})

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.succeeded
        assert updated.result == fake_result
    finally:
        session.close()


def test_process_job_marks_failed_on_unexpected_error(
    pool, store, queued_job, SessionLocal
):
    with patch(
        "app.workers.pool.run_inference",
        side_effect=RuntimeError("boom"),
    ):
        pool._process_job(queued_job.id)

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.failed
        assert updated.result == {
            "error": "boom",
            "code": "unexpected_error",
            "retryable": False,
        }
    finally:
        session.close()


def test_process_job_marks_failed_on_typed_inference_error(
    pool, store, queued_job, SessionLocal
):
    with patch(
        "app.workers.pool.run_inference",
        side_effect=ProviderAuthError("bad key"),
    ):
        pool._process_job(queued_job.id)

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.failed
        assert updated.result["code"] == "provider_auth_error"
        assert updated.result["retryable"] is False
        assert updated.result["error"] == "bad key"
    finally:
        session.close()


def test_process_job_marks_failed_on_invalid_payload(
    pool, store, queued_job, SessionLocal
):
    with patch(
        "app.workers.pool.run_inference",
        side_effect=PayloadValidationError("bad payload"),
    ):
        pool._process_job(queued_job.id)

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.failed
        assert updated.result["code"] == "invalid_payload"
        assert updated.result["retryable"] is False
    finally:
        session.close()


def test_process_job_skips_missing_id(pool):
    pool._process_job("does-not-exist")


def test_process_job_skips_non_queued(pool, db, store, queued_job, SessionLocal):
    # Already claimed / running — atomic claim should no-op.
    claimed = store.claim_queued(queued_job.id, db)
    assert claimed is not None

    with patch("app.workers.pool.run_inference") as mock_infer:
        pool._process_job(queued_job.id)
        mock_infer.assert_not_called()

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.running
        assert updated.result is None
    finally:
        session.close()


def test_worker_loop_survives_process_crash(pool):
    with patch.object(pool, "_process_job", side_effect=RuntimeError("explode")):
        pool.start()
        try:
            pool.enqueue("any-id")
            pool._queue.join()
        finally:
            pool.stop(timeout=2.0)

    # Pool should still accept stop cleanly (thread stayed alive).
    assert pool._started is False


def test_enqueue_and_worker_processes_job(pool, store, queued_job, SessionLocal):
    fake_result = {"provider": "digitalocean", "content": "done"}

    with patch("app.workers.pool.run_inference", return_value=fake_result):
        pool.start()
        try:
            pool.enqueue(queued_job.id)
            pool._queue.join()
        finally:
            pool.stop(timeout=2.0)

    session = SessionLocal()
    try:
        updated = store.get(queued_job.id, session)
        assert updated is not None
        assert updated.status == JobStatus.succeeded
        assert updated.result == fake_result
    finally:
        session.close()
