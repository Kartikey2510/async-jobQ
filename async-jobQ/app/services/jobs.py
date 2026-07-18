import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.store.jobs import JobStore, job_store
from app.workers.pool import worker_pool


class JobNotFoundError(Exception):
    """Raised when a job id is not in the store."""


def create_job(
    payload: Dict[str, Any],
    db: Session,
    store: JobStore = job_store,
) -> Job:
    """Accept a payload, persist a queued job, enqueue for background processing."""
    now = datetime.utcnow()
    job = Job(
        id=str(uuid.uuid4()),
        status=JobStatus.queued,
        payload=payload,
        result=None,
        created_at=now,
        updated_at=now,
    )
    stored = store.save(job, db)
    worker_pool.enqueue(stored.id)
    return stored


def get_job(job_id: str, db: Session, store: JobStore = job_store) -> Job:
    """Look up a job by id. Raises JobNotFoundError if missing."""
    job = store.get(job_id, db)
    if job is None:
        raise JobNotFoundError(job_id)
    return job
