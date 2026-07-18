from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import JobCreateRequest, JobCreateResponse, JobResponse
from app.services import jobs as jobs_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    body: JobCreateRequest,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    job = jobs_service.create_job(body.root, db)
    return JobCreateResponse(id=job.id)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    try:
        job = jobs_service.get_job(job_id, db)
    except jobs_service.JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        ) from None

    return JobResponse(
        id=job.id,
        status=job.status,
        result=job.result,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
