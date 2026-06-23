from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, ensure_utc
from app.schemas import JobCreate

TERMINAL_STATUSES = {
    JobStatus.canceled.value,
    JobStatus.succeeded.value,
    JobStatus.failed.value,
    JobStatus.dead_lettered.value,
}


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, request: JobCreate) -> Job:
        job, _ = self.create_if_absent(request)
        return job

    def create_if_absent(self, request: JobCreate) -> tuple[Job, bool]:
        if request.idempotency_key:
            existing = self.get_by_idempotency_key(request.idempotency_key)
            if existing:
                return existing, False

        job = Job(
            queue_name=request.queue_name,
            job_type=request.job_type,
            payload=request.payload,
            priority=request.priority,
            max_attempts=request.max_attempts,
            scheduled_at=request.scheduled_at or datetime.now(UTC),
            idempotency_key=request.idempotency_key,
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if not request.idempotency_key:
                raise
            existing = self.get_by_idempotency_key(request.idempotency_key)
            if not existing:
                raise
            return existing, False
        self.db.refresh(job)
        return job, True

    def get(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def get_by_idempotency_key(self, key: str) -> Job | None:
        return self.db.scalar(select(Job).where(Job.idempotency_key == key))

    def cancel(self, job: Job) -> Job:
        if job.status in TERMINAL_STATUSES - {JobStatus.canceled.value}:
            return job
        job.status = JobStatus.canceled.value
        job.finished_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(job)
        return job

    def acquire(self, job: Job, worker_id: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=lease_seconds)
        started_at = ensure_utc(job.started_at) if job.started_at else now
        result = self.db.execute(
            update(Job)
            .where(Job.id == job.id)
            .where(~Job.status.in_(TERMINAL_STATUSES))
            .where(Job.scheduled_at <= now)
            .where(or_(Job.locked_until.is_(None), Job.locked_until <= now))
            .where(
                or_(
                    Job.status.in_([JobStatus.queued.value, JobStatus.retrying.value]),
                    and_(
                        Job.status == JobStatus.running.value,
                        Job.locked_until <= now,
                    ),
                )
            )
            .values(
                status=JobStatus.running.value,
                locked_by=worker_id,
                locked_until=locked_until,
                started_at=started_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            return False

        self.db.commit()
        self.db.refresh(job)
        return True

    def mark_succeeded(self, job: Job, result: dict | None = None) -> Job:
        job.status = JobStatus.succeeded.value
        job.result = result or {}
        job.error = None
        job.finished_at = datetime.now(UTC)
        job.locked_by = None
        job.locked_until = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed_or_retrying(self, job: Job, error: str) -> Job:
        job.attempt_count += 1
        job.error = error
        job.locked_by = None
        job.locked_until = None
        if job.attempt_count >= job.max_attempts:
            job.status = JobStatus.dead_lettered.value
            job.finished_at = datetime.now(UTC)
        else:
            job.status = JobStatus.retrying.value
        self.db.commit()
        self.db.refresh(job)
        return job
