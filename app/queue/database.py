from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select

from app.db.models import Job, JobStatus
from app.db.session import SessionLocal
from app.queue.base import JobQueue


class DatabaseJobQueue(JobQueue):
    def enqueue(
        self,
        queue_name: str,
        job_id: str,
        *,
        priority: int = 0,
        scheduled_at: datetime | None = None,
    ) -> None:
        return None

    def dequeue(self, queue_names: Iterable[str]) -> str | None:
        names = list(queue_names)
        if not names:
            return None

        now = datetime.now(UTC)
        with SessionLocal() as db:
            return db.scalar(
                select(Job.id)
                .where(Job.queue_name.in_(names))
                .where(
                    or_(
                        Job.status.in_(
                            [JobStatus.queued.value, JobStatus.retrying.value]
                        ),
                        and_(
                            Job.status == JobStatus.running.value,
                            Job.locked_until <= now,
                        ),
                    )
                )
                .where(Job.scheduled_at <= now)
                .where(or_(Job.locked_until.is_(None), Job.locked_until <= now))
                .order_by(
                    Job.priority.desc(), Job.scheduled_at.asc(), Job.created_at.asc()
                )
                .limit(1)
            )
