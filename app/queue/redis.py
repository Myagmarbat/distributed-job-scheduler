from collections.abc import Iterable
from datetime import UTC, datetime

from redis import Redis

from app.queue.base import JobQueue
from app.queue.database import DatabaseJobQueue


class RedisJobQueue(JobQueue):
    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str = "scheduler",
        dequeue_batch_size: int = 100,
        fallback_queue: JobQueue | None = None,
    ) -> None:
        self.client = client
        self.key_prefix = key_prefix
        self.dequeue_batch_size = dequeue_batch_size
        self.fallback_queue = fallback_queue or DatabaseJobQueue()

    def enqueue(
        self,
        queue_name: str,
        job_id: str,
        *,
        priority: int = 0,
        scheduled_at: datetime | None = None,
    ) -> None:
        scheduled = scheduled_at or datetime.now(UTC)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)

        metadata_key = self._metadata_key(queue_name)
        ready_key = self._ready_key(queue_name)

        pipe = self.client.pipeline()
        pipe.hset(metadata_key, job_id, str(priority))
        pipe.zadd(ready_key, {job_id: scheduled.timestamp()})
        pipe.execute()

    def dequeue(self, queue_names: Iterable[str]) -> str | None:
        now = datetime.now(UTC).timestamp()
        for queue_name in queue_names:
            job_id = self._dequeue_from_queue(queue_name, now)
            if job_id:
                return job_id
        return self.fallback_queue.dequeue(queue_names)

    def _dequeue_from_queue(self, queue_name: str, now: float) -> str | None:
        ready_key = self._ready_key(queue_name)
        metadata_key = self._metadata_key(queue_name)

        candidates = self.client.zrangebyscore(
            ready_key,
            min="-inf",
            max=now,
            start=0,
            num=self.dequeue_batch_size,
        )
        if not candidates:
            return None

        decoded = [self._decode(candidate) for candidate in candidates]
        priorities = self.client.hmget(metadata_key, decoded)
        ranked = [
            (job_id, int(priority or 0))
            for job_id, priority in zip(decoded, priorities, strict=True)
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)

        for job_id, _priority in ranked:
            if self.client.zrem(ready_key, job_id) == 1:
                self.client.hdel(metadata_key, job_id)
                return job_id
        return None

    def _ready_key(self, queue_name: str) -> str:
        return f"{self.key_prefix}:queue:{queue_name}:ready"

    def _metadata_key(self, queue_name: str) -> str:
        return f"{self.key_prefix}:queue:{queue_name}:metadata"

    @staticmethod
    def _decode(value: str | bytes) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return value
