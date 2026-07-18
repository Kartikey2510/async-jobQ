"""Shared fixtures for worker / store tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import orm  # noqa: F401 — register JobRecord on metadata
from app.models.job import Job, JobStatus
from app.store.jobs import JobStore
from datetime import datetime
import uuid


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def SessionLocal(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def db(SessionLocal):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def store():
    return JobStore()


@pytest.fixture
def queued_job(db, store):
    now = datetime.utcnow()
    job = Job(
        id=str(uuid.uuid4()),
        status=JobStatus.queued,
        payload={"prompt": "Say hello"},
        result=None,
        created_at=now,
        updated_at=now,
    )
    return store.save(job, db)
