from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import UTC, datetime
from threading import Lock

from app.queue.base import JobQueue


class InMemoryJobQueue(JobQueue):
    def __init__(self) -> None:
        self._queues: dict[str, deque[tuple[str, int, datetime]]] = defaultdict(deque)
        self._queued_ids: set[str] = set()
        self._lock = Lock()

    def enqueue(
        self,
        queue_name: str,
        job_id: str,
        *,
        priority: int = 0,
        scheduled_at: datetime | None = None,
    ) -> None:
        with self._lock:
            if job_id in self._queued_ids:
                return
            self._queues[queue_name].append(
                (job_id, priority, scheduled_at or datetime.now(UTC))
            )
            self._queued_ids.add(job_id)

    def dequeue(self, queue_names: Iterable[str]) -> str | None:
        now = datetime.now(UTC)
        with self._lock:
            for queue_name in queue_names:
                ready = [
                    (index, item)
                    for index, item in enumerate(self._queues[queue_name])
                    if item[2] <= now
                ]
                if not ready:
                    continue

                index, (job_id, _priority, _scheduled_at) = max(
                    ready,
                    key=lambda candidate: (
                        candidate[1][1],
                        -candidate[1][2].timestamp(),
                    ),
                )
                del self._queues[queue_name][index]
                self._queued_ids.discard(job_id)
                return job_id
        return None
