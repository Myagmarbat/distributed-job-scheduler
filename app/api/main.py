from datetime import datetime
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job, JobStatus
from app.db.repository import JobRepository
from app.db.session import Base, engine, get_db
from app.queue import get_queue
from app.schemas import JobCreate, JobCreated, JobOut

settings = get_settings()
DbSession = Annotated[Session, Depends(get_db)]
logger = structlog.get_logger()

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("readiness_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ready"}


@app.post("/jobs", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
def create_job(request: JobCreate, db: DbSession) -> JobCreated:
    repo = JobRepository(db)
    job, created = repo.create_if_absent(request)
    if created:
        get_queue().enqueue(
            job.queue_name,
            job.id,
            priority=job.priority,
            scheduled_at=job.scheduled_at,
        )
    logger.info(
        "job_created" if created else "job_create_idempotent",
        job_id=job.id,
        job_type=job.job_type,
        queue_name=job.queue_name,
        state=job.status,
        attempt=job.attempt_count,
        idempotency_key=job.idempotency_key,
    )
    return JobCreated(id=job.id, status=job.status)


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: DbSession) -> JobOut:
    job = JobRepository(db).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(job)


@app.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: DbSession) -> JobOut:
    repo = JobRepository(db)
    job = repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    canceled = repo.cancel(job)
    logger.info(
        "job_cancel_requested",
        job_id=canceled.id,
        job_type=canceled.job_type,
        queue_name=canceled.queue_name,
        state=canceled.status,
        attempt=canceled.attempt_count,
    )
    return JobOut.model_validate(canceled)


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(
    response: Response,
    db: DbSession,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    status_filter: Annotated[
        JobStatus | None, Query(deprecated=True)
    ] = None,
    queue_name: str | None = None,
    job_type: str | None = None,
    idempotency_key: str | None = None,
    scheduled_before: datetime | None = None,
    scheduled_after: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobOut]:
    status_value = job_status or status_filter
    response.headers["X-Note"] = "Pagination is planned after MVP."
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    statement = select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
    if status_value:
        statement = statement.where(Job.status == status_value.value)
    if queue_name:
        statement = statement.where(Job.queue_name == queue_name)
    if job_type:
        statement = statement.where(Job.job_type == job_type)
    if idempotency_key:
        statement = statement.where(Job.idempotency_key == idempotency_key)
    if scheduled_before:
        statement = statement.where(Job.scheduled_at <= scheduled_before)
    if scheduled_after:
        statement = statement.where(Job.scheduled_at >= scheduled_after)
    return [JobOut.model_validate(job) for job in db.scalars(statement)]
