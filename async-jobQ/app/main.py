"""Async job queue API.

Jobs are accepted immediately, stored in SQLite, and processed by an in-process
worker pool that calls DigitalOcean Serverless Inference.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env from project root (async-jobQ/), not the process cwd.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

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
