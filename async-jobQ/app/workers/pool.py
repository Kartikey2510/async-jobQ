"""In-process job queue and worker pool."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import List, Optional

from app.db import SessionLocal
from app.models.job import JobStatus
from app.store.jobs import job_store

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
                self._process_job(str(item))
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            job = job_store.get(job_id, db)
            if job is None:
                logger.warning("Job %s not found; skipping", job_id)
                return
            if job.status != JobStatus.queued:
                logger.info("Job %s status is %s; skipping", job_id, job.status)
                return

            job.status = JobStatus.running
            job_store.update(job, db)

            try:
                # Mock processing — replace with real work (e.g. LLM) later.
                time.sleep(3)
                result = {"echo": job.payload, "processed": True}
                job.status = JobStatus.succeeded
                job.result = result
                job_store.update(job, db)
                logger.info("Job %s succeeded", job_id)
            except Exception as exc:  # noqa: BLE001 — persist failure on the job
                logger.exception("Job %s failed", job_id)
                job.status = JobStatus.failed
                job.result = {"error": str(exc)}
                job_store.update(job, db)
        finally:
            db.close()


worker_pool = WorkerPool(num_workers=2)
