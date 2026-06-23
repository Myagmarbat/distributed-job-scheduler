import time
from collections.abc import Iterable

import structlog

from app.core.config import get_settings
from app.db.repository import JobRepository
from app.db.session import SessionLocal
from app.queue import get_queue
from app.queue.base import JobQueue
from app.worker.handlers import HandlerRegistry, registry

logger = structlog.get_logger()


def _job_log_context(job, worker_id: str) -> dict[str, object]:
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "queue_name": job.queue_name,
        "state": job.status,
        "attempt": job.attempt_count,
        "worker_id": worker_id,
    }


class Worker:
    def __init__(
        self,
        queue: JobQueue | None = None,
        handlers: HandlerRegistry = registry,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.queue = queue or get_queue()
        self.handlers = handlers
        self.worker_id = worker_id or settings.worker_id
        self.lease_seconds = lease_seconds or settings.lease_seconds

    def run_once(self, queue_names: Iterable[str] = ("default",)) -> bool:
        job_id = self.queue.dequeue(queue_names)
        if not job_id:
            return False

        with SessionLocal() as db:
            repo = JobRepository(db)
            job = repo.get(job_id)
            if not job:
                logger.warning(
                    "job_missing",
                    job_id=job_id,
                    worker_id=self.worker_id,
                )
                return True
            if not repo.acquire(job, self.worker_id, self.lease_seconds):
                logger.info(
                    "job_claim_skipped",
                    **_job_log_context(job, self.worker_id),
                )
                return True

            logger.info("job_started", **_job_log_context(job, self.worker_id))
            try:
                handler = self.handlers.get(job.job_type)
                result = handler(job.payload)
            except Exception as exc:  # noqa: BLE001
                failed_job = repo.mark_failed_or_retrying(job, str(exc))
                event_name = (
                    "job_dead_lettered"
                    if failed_job.status == "dead_lettered"
                    else "job_retrying"
                )
                logger.exception(
                    event_name,
                    error=str(exc),
                    **_job_log_context(failed_job, self.worker_id),
                )
                return True

            succeeded_job = repo.mark_succeeded(job, result)
            logger.info(
                "job_succeeded",
                **_job_log_context(succeeded_job, self.worker_id),
            )
            return True

    def run_forever(
        self, queue_names: Iterable[str] = ("default",), idle_seconds: float = 1.0
    ) -> None:
        while True:
            did_work = self.run_once(queue_names)
            if not did_work:
                time.sleep(idle_seconds)
