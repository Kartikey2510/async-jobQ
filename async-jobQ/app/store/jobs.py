"""SQLAlchemy-backed job store."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.models.orm import JobRecord


class JobStore:
    def save(self, job: Job, db: Session) -> Job:
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
        record = db.get(JobRecord, job_id)
        if record is None:
            return None
        return self._to_job(record)

    def update(self, job: Job, db: Session) -> Job:
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
