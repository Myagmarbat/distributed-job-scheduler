from datetime import UTC, datetime, timedelta


def test_worker_executes_echo_job(client):
    response = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"message": "hello"}},
    )
    job_id = response.json()["id"]

    from app.worker.runtime import Worker

    did_work = Worker(worker_id="test-worker").run_once()

    assert did_work is True
    response = client.get(f"/jobs/{job_id}")
    assert response.json()["status"] == "succeeded"
    assert response.json()["result"] == {"echo": {"message": "hello"}}


def test_worker_logs_lifecycle_context(client, monkeypatch):
    response = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"message": "hello"}},
    )
    job_id = response.json()["id"]

    from app.worker import runtime

    events = []

    class FakeLogger:
        def info(self, event, **fields):
            events.append((event, fields))

        def warning(self, event, **fields):
            events.append((event, fields))

        def exception(self, event, **fields):
            events.append((event, fields))

    monkeypatch.setattr(runtime, "logger", FakeLogger())

    assert runtime.Worker(worker_id="test-worker").run_once() is True

    assert events == [
        (
            "job_started",
            {
                "job_id": job_id,
                "job_type": "echo",
                "queue_name": "default",
                "state": "running",
                "attempt": 0,
                "worker_id": "test-worker",
            },
        ),
        (
            "job_succeeded",
            {
                "job_id": job_id,
                "job_type": "echo",
                "queue_name": "default",
                "state": "succeeded",
                "attempt": 0,
                "worker_id": "test-worker",
            },
        ),
    ]


def test_worker_returns_false_when_no_jobs_are_ready(client):
    from app.worker.runtime import Worker

    did_work = Worker(worker_id="test-worker").run_once()

    assert did_work is False


def test_worker_marks_job_retrying_before_eventual_success(client):
    from app.worker.handlers import HandlerRegistry
    from app.worker.runtime import Worker

    attempts = {"count": 0}
    handlers = HandlerRegistry()

    def flaky_handler(payload):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary failure")
        return {"ok": payload["value"]}

    handlers.register("flaky", flaky_handler)
    response = client.post(
        "/jobs",
        json={"job_type": "flaky", "payload": {"value": 42}, "max_attempts": 2},
    )
    job_id = response.json()["id"]
    worker = Worker(handlers=handlers, worker_id="test-worker")

    assert worker.run_once() is True
    retrying = client.get(f"/jobs/{job_id}").json()
    assert retrying["status"] == "retrying"
    assert retrying["attempt_count"] == 1
    assert retrying["error"] == "temporary failure"

    assert worker.run_once() is True
    succeeded = client.get(f"/jobs/{job_id}").json()
    assert succeeded["status"] == "succeeded"
    assert succeeded["attempt_count"] == 1
    assert succeeded["result"] == {"ok": 42}
    assert succeeded["error"] is None


def test_worker_dead_letters_after_max_attempts(client):
    from app.worker.handlers import HandlerRegistry
    from app.worker.runtime import Worker

    handlers = HandlerRegistry()

    def fail_handler(payload):
        raise RuntimeError("boom")

    handlers.register("fail", fail_handler)
    response = client.post("/jobs", json={"job_type": "fail", "max_attempts": 1})
    job_id = response.json()["id"]

    did_work = Worker(handlers=handlers, worker_id="test-worker").run_once()

    assert did_work is True
    response = client.get(f"/jobs/{job_id}")
    assert response.json()["status"] == "dead_lettered"
    assert response.json()["attempt_count"] == 1
    assert response.json()["error"] == "boom"


def test_worker_dead_letters_unregistered_job_type(client):
    response = client.post(
        "/jobs",
        json={"job_type": "missing-handler", "max_attempts": 1},
    )
    job_id = response.json()["id"]

    from app.worker.runtime import Worker

    assert Worker(worker_id="test-worker").run_once() is True

    response = client.get(f"/jobs/{job_id}")
    assert response.json()["status"] == "dead_lettered"
    assert response.json()["attempt_count"] == 1
    assert (
        "no handler registered for job_type=missing-handler" in response.json()["error"]
    )


def test_worker_skips_canceled_job(client):
    response = client.post("/jobs", json={"job_type": "echo"})
    job_id = response.json()["id"]
    client.post(f"/jobs/{job_id}/cancel")

    from app.worker.runtime import Worker

    did_work = Worker(worker_id="test-worker").run_once()

    assert did_work is False
    assert client.get(f"/jobs/{job_id}").json()["status"] == "canceled"


def test_worker_respects_requested_queue_names(client):
    default_job = client.post("/jobs", json={"job_type": "echo"}).json()
    fast_job = client.post(
        "/jobs",
        json={
            "job_type": "echo",
            "queue_name": "fast",
            "payload": {"queue": "fast"},
        },
    ).json()

    from app.worker.runtime import Worker

    assert Worker(worker_id="test-worker").run_once(queue_names=("fast",)) is True

    assert client.get(f"/jobs/{fast_job['id']}").json()["status"] == "succeeded"
    assert client.get(f"/jobs/{default_job['id']}").json()["status"] == "queued"


def test_worker_prefers_highest_priority_ready_job(client):
    low_job = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"priority": "low"}, "priority": 0},
    ).json()
    high_job = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"priority": "high"}, "priority": 10},
    ).json()

    from app.worker.runtime import Worker

    assert Worker(worker_id="test-worker").run_once() is True

    assert client.get(f"/jobs/{high_job['id']}").json()["status"] == "succeeded"
    assert client.get(f"/jobs/{low_job['id']}").json()["status"] == "queued"


def test_worker_ignores_future_scheduled_job_until_due(client):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    response = client.post(
        "/jobs",
        json={"job_type": "echo", "scheduled_at": future},
    )
    job_id = response.json()["id"]

    from app.worker.runtime import Worker

    assert Worker(worker_id="test-worker").run_once() is False
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"


def test_repository_lease_blocks_other_workers_until_expired(client):
    from app.db.repository import JobRepository
    from app.db.session import SessionLocal
    from app.schemas import JobCreate

    with SessionLocal() as db:
        repo = JobRepository(db)
        job = repo.create(JobCreate(job_type="echo"))
        job_id = job.id

        assert repo.acquire(job, worker_id="worker-a", lease_seconds=60) is True
        assert repo.acquire(job, worker_id="worker-b", lease_seconds=60) is False

        job.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        assert repo.acquire(job, worker_id="worker-b", lease_seconds=60) is True

    response = client.get(f"/jobs/{job_id}")
    assert response.json()["status"] == "running"
