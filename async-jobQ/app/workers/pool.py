"""In-process job queue and worker pool."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.job import Job, JobStatus
from app.store.jobs import job_store
from app.workers.errors import InferenceError
from app.workers.inference import run_inference

logger = logging.getLogger(__name__)

# Sentinel that tells a worker thread to exit.
_STOP = object()


class WorkerPool:
    """Fixed-size thread pool that pulls job ids from an in-process queue."""

    def __init__(self, num_workers: int = 2) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._num_workers = num_workers
        self._threads: List[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._threads = []
            for i in range(self._num_workers):
                thread = threading.Thread(
                    target=self._worker_loop,
                    name=f"job-worker-{i}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)
            self._started = True
            logger.info("Worker pool started with %s workers", self._num_workers)

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._started:
                return
            for _ in self._threads:
                self._queue.put(_STOP)
            for thread in self._threads:
                thread.join(timeout=timeout)
            self._threads = []
            self._started = False
            logger.info("Worker pool stopped")

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                try:
                    self._process_job(str(item))
                except Exception:  # noqa: BLE001 — keep worker alive
                    logger.exception(
                        "Unhandled error while processing queue item %r", item
                    )
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        db = SessionLocal()
        job: Optional[Job] = None
        try:
            try:
                job = job_store.get(job_id, db)
            except Exception:
                logger.exception("Failed to load job %s from store", job_id)
                return

            if job is None:
                logger.warning("Job %s not found; skipping", job_id)
                return
            if job.status != JobStatus.queued:
                logger.info("Job %s status is %s; skipping", job_id, job.status)
                return

            if not self._mark_status(job, JobStatus.running, db):
                return

            try:
                logger.info("Job %s calling DigitalOcean inference", job_id)
                result = run_inference(job.payload)
                job.status = JobStatus.succeeded
                job.result = result
                if not self._persist(job, db):
                    logger.error(
                        "Job %s succeeded in inference but failed to persist result",
                        job_id,
                    )
                    return
                logger.info("Job %s succeeded result=%s", job_id, result)
            except InferenceError as exc:
                logger.error(
                    "Job %s failed code=%s retryable=%s error=%s",
                    job_id,
                    exc.code,
                    exc.retryable,
                    exc.message,
                )
                self._fail_job(job, exc.to_result(), db)
            except Exception as exc:  # noqa: BLE001 — unexpected failures
                logger.exception("Job %s failed with unexpected error", job_id)
                self._fail_job(
                    job,
                    {
                        "error": str(exc),
                        "code": "unexpected_error",
                        "retryable": False,
                    },
                    db,
                )
        finally:
            db.close()

    def _mark_status(self, job: Job, status: JobStatus, db: Session) -> bool:
        job.status = status
        return self._persist(job, db)

    def _fail_job(self, job: Job, result: Dict[str, Any], db: Session) -> None:
        job.status = JobStatus.failed
        job.result = result
        if not self._persist(job, db):
            logger.error("Job %s could not persist failure state: %s", job.id, result)

    @staticmethod
    def _persist(job: Job, db: Session) -> bool:
        try:
            job_store.update(job, db)
            return True
        except Exception:
            logger.exception("Failed to persist job %s status=%s", job.id, job.status)
            try:
                db.rollback()
            except Exception:
                logger.exception("Rollback failed for job %s", job.id)
            return False


worker_pool = WorkerPool(num_workers=2)
