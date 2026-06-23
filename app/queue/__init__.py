from functools import lru_cache

from app.core.config import get_settings
from app.queue.base import JobQueue
from app.queue.database import DatabaseJobQueue
from app.queue.memory import InMemoryJobQueue
from app.queue.redis import RedisJobQueue


@lru_cache
def get_queue() -> JobQueue:
    backend = get_settings().queue_backend.lower()
    if backend == "database":
        return DatabaseJobQueue()
    if backend in {"memory", "in_memory"}:
        return InMemoryJobQueue()
    if backend in {"redis", "valkey"}:
        from redis import Redis

        settings = get_settings()
        return RedisJobQueue(
            Redis.from_url(settings.redis_url),
            dequeue_batch_size=settings.redis_dequeue_batch_size,
        )
    raise ValueError(f"unsupported queue backend: {backend}")
