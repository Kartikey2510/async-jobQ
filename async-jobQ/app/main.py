"""Async job queue API.

Jobs are accepted immediately, stored in SQLite, and processed by an in-process worker pool.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes.jobs import router as jobs_router
from app.workers.pool import worker_pool


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    worker_pool.start()
    yield
    worker_pool.stop()


app = FastAPI(title="Job Queue API", version="0.1.0", lifespan=lifespan)
app.include_router(jobs_router)
