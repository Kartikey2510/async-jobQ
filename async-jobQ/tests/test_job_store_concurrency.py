"""Unit tests for atomic job store transitions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.models.job import JobStatus


def test_claim_queued_is_atomic(store, queued_job, SessionLocal):
    s1 = SessionLocal()
    s2 = SessionLocal()
    try:
        first = store.claim_queued(queued_job.id, s1)
        second = store.claim_queued(queued_job.id, s2)

        assert first is not None
        assert first.status == JobStatus.running
        assert second is None
    finally:
        s1.close()
        s2.close()


def test_claim_queued_concurrent_only_one_wins(store, queued_job, SessionLocal):
    def attempt(_):
        session = SessionLocal()
        try:
            return store.claim_queued(queued_job.id, session)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert winners[0].status == JobStatus.running


def test_complete_writes_status_and_result_together(
    store, queued_job, SessionLocal
):
    session = SessionLocal()
    try:
        claimed = store.claim_queued(queued_job.id, session)
        assert claimed is not None

        result = {"content": "hi"}
        completed = store.complete(
            queued_job.id,
            status=JobStatus.succeeded,
            result=result,
            db=session,
        )
        assert completed is not None
        assert completed.status == JobStatus.succeeded
        assert completed.result == result

        # Second complete must fail — no longer running.
        again = store.complete(
            queued_job.id,
            status=JobStatus.failed,
            result={"error": "nope"},
            db=session,
        )
        assert again is None

        final = store.get(queued_job.id, session)
        assert final is not None
        assert final.status == JobStatus.succeeded
        assert final.result == result
    finally:
        session.close()
