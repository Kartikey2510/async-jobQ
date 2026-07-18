from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, RootModel, model_validator


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: JobStatus
    payload: Dict[str, Any]
    result: Optional[Any] = None
    created_at: datetime
    updated_at: datetime


class JobCreateRequest(RootModel[Dict[str, Any]]):
    """POST /jobs body: a non-empty JSON object with at least one non-null value."""

    @model_validator(mode="after")
    def validate_payload(self) -> "JobCreateRequest":
        if not self.root:
            raise ValueError("payload must be a non-empty JSON object")
        if all(value is None for value in self.root.values()):
            raise ValueError("payload must include at least one non-null value")
        return self


class JobCreateResponse(BaseModel):
    id: str


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    result: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
