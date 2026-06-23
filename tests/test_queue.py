from datetime import UTC, datetime, timedelta


class FakeRedisPipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def hset(self, *args):
        self.calls.append(("hset", args))
        return self

    def zadd(self, *args):
        self.calls.append(("zadd", args))
        return self

    def execute(self):
        for method_name, args in self.calls:
            getattr(self.redis, method_name)(*args)


class FakeRedis:
    def __init__(self):
        self.sorted_sets = {}
        self.hashes = {}

    def pipeline(self):
        return FakeRedisPipeline(self)

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)

    def zrangebyscore(self, key, min, max, start=0, num=None):
        del min
        members = [
            member
            for member, score in self.sorted_sets.get(key, {}).items()
            if score <= max
        ]
        members.sort(key=lambda member: self.sorted_sets[key][member])
        end = None if num is None else start + num
        return members[start:end]

    def hmget(self, key, fields):
        return [self.hashes.get(key, {}).get(field) for field in fields]

    def zrem(self, key, member):
        removed = self.sorted_sets.get(key, {}).pop(member, None)
        return 1 if removed is not None else 0

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)


class EmptyFallbackQueue:
    def dequeue(self, queue_names):
        del queue_names
        return None


def test_memory_queue_respects_priority_and_schedule():
    from app.queue.memory import InMemoryJobQueue

    queue = InMemoryJobQueue()
    now = datetime.now(UTC)
    queue.enqueue("default", "low", priority=1, scheduled_at=now)
    queue.enqueue(
        "default",
        "future",
        priority=100,
        scheduled_at=now + timedelta(hours=1),
    )
    queue.enqueue("default", "high", priority=10, scheduled_at=now)

    assert queue.dequeue(("default",)) == "high"
    assert queue.dequeue(("default",)) == "low"
    assert queue.dequeue(("default",)) is None


def test_redis_queue_respects_priority_and_schedule():
    from app.queue.redis import RedisJobQueue

    redis = FakeRedis()
    queue = RedisJobQueue(redis, fallback_queue=EmptyFallbackQueue())
    now = datetime.now(UTC)
    queue.enqueue("default", "low", priority=1, scheduled_at=now)
    queue.enqueue(
        "default",
        "future",
        priority=100,
        scheduled_at=now + timedelta(hours=1),
    )
    queue.enqueue("default", "high", priority=10, scheduled_at=now)

    assert queue.dequeue(("default",)) == "high"
    assert queue.dequeue(("default",)) == "low"
    assert queue.dequeue(("default",)) is None


def test_redis_queue_falls_back_when_delivery_queue_is_empty():
    from app.queue.redis import RedisJobQueue

    class FallbackQueue:
        def dequeue(self, queue_names):
            assert tuple(queue_names) == ("default",)
            return "db-job"

    queue = RedisJobQueue(FakeRedis(), fallback_queue=FallbackQueue())

    assert queue.dequeue(("default",)) == "db-job"


def test_get_queue_supports_valkey_backend(monkeypatch):
    import app.queue as queue_module
    from app.core.config import Settings
    from app.queue.redis import RedisJobQueue

    class FakeRedisFactory:
        @staticmethod
        def from_url(url):
            assert url == "redis://valkey:6379/0"
            return FakeRedis()

    monkeypatch.setattr(
        queue_module,
        "get_settings",
        lambda: Settings(queue_backend="valkey", redis_url="redis://valkey:6379/0"),
    )
    monkeypatch.setattr("redis.Redis", FakeRedisFactory)
    queue_module.get_queue.cache_clear()

    try:
        assert isinstance(queue_module.get_queue(), RedisJobQueue)
    finally:
        queue_module.get_queue.cache_clear()
