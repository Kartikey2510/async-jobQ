"""SQLAlchemy-backed job store with atomic status transitions."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.models.orm import JobRecord


class JobStore:
    """Job persistence.

    Mutations are serialized with a process-local lock (safe for SQLite + threads)
    and use conditional UPDATEs so only one worker can claim/complete a job.
    """

    def __init__(self) -> None:
        self._write_lock = threading.RLock()

    def save(self, job: Job, db: Session) -> Job:
        """Insert a new job. Must complete before enqueueing for workers."""
        with self._write_lock:
            record = JobRecord(
                id=job.id,
                status=job.status.value,
                payload=job.payload,
                result=job.result,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return self._to_job(record)

    def get(self, job_id: str, db: Session) -> Optional[Job]:
        """Read a committed job snapshot (safe for concurrent HTTP polls)."""
        db.expire_all()
        record = db.get(JobRecord, job_id)
        if record is None:
            return None
        return self._to_job(record)

    def claim_queued(self, job_id: str, db: Session) -> Optional[Job]:
        """Atomically claim a job: queued → running.

        Returns the claimed job, or None if missing / already claimed.
        Only one concurrent caller can win this transition.
        """
        with self._write_lock:
            now = datetime.utcnow()
            result = db.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status == JobStatus.queued.value,
                )
                .values(status=JobStatus.running.value, updated_at=now)
            )
            db.commit()
            if result.rowcount != 1:
                return None
            return self.get(job_id, db)

    def complete(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result: Any,
        db: Session,
        expected_status: JobStatus = JobStatus.running,
    ) -> Optional[Job]:
        """Atomically finish a job if it is still in expected_status (usually running).

        Writes status + result in one UPDATE so HTTP never observes
        succeeded/failed without a result (or vice versa).
        """
        if status not in (JobStatus.succeeded, JobStatus.failed):
            raise ValueError(f"complete() requires terminal status, got {status}")

        with self._write_lock:
            now = datetime.utcnow()
            exec_result = db.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job_id,
                    JobRecord.status == expected_status.value,
                )
                .values(status=status.value, result=result, updated_at=now)
            )
            db.commit()
            if exec_result.rowcount != 1:
                return None
            return self.get(job_id, db)

    def update(self, job: Job, db: Session) -> Job:
        """Full replace update (tests / admin). Prefer claim_queued/complete in workers."""
        with self._write_lock:
            record = db.get(JobRecord, job.id)
            if record is None:
                raise KeyError(f"Job not found: {job.id}")

            record.status = job.status.value
            record.payload = job.payload
            record.result = job.result
            record.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(record)
            return self._to_job(record)

    @staticmethod
    def _to_job(record: JobRecord) -> Job:
        return Job(
            id=record.id,
            status=JobStatus(record.status),
            payload=record.payload,
            result=record.result,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


job_store = JobStore()
