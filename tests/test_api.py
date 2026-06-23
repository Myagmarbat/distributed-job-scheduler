from datetime import datetime

from sqlalchemy.exc import OperationalError


def test_create_and_get_job(client):
    response = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"message": "hello"}},
    )

    assert response.status_code == 201
    job_id = response.json()["id"]

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["payload"] == {"message": "hello"}


def test_health_and_readiness_endpoints(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}


def test_readiness_returns_503_when_database_probe_fails(client):
    from app.api import main as api_main

    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("database down"))

    api_main.app.dependency_overrides[api_main.get_db] = lambda: BrokenSession()
    try:
        response = client.get("/readyz")
    finally:
        api_main.app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"


def test_create_job_logs_lifecycle_context(client, monkeypatch):
    from app.api import main as api_main

    events = []

    class FakeLogger:
        def info(self, event, **fields):
            events.append((event, fields))

    monkeypatch.setattr(api_main, "logger", FakeLogger())

    response = client.post(
        "/jobs",
        json={"job_type": "echo", "payload": {"message": "hello"}},
    )

    assert response.status_code == 201
    assert events == [
        (
            "job_created",
            {
                "job_id": response.json()["id"],
                "job_type": "echo",
                "queue_name": "default",
                "state": "queued",
                "attempt": 0,
                "idempotency_key": None,
            },
        )
    ]


def test_create_job_enqueues_priority_and_schedule(client, monkeypatch):
    from app.api import main as api_main

    calls = []

    class FakeQueue:
        def enqueue(self, queue_name, job_id, *, priority=0, scheduled_at=None):
            calls.append(
                {
                    "queue_name": queue_name,
                    "job_id": job_id,
                    "priority": priority,
                    "scheduled_at": scheduled_at,
                }
            )

    monkeypatch.setattr(api_main, "get_queue", lambda: FakeQueue())
    scheduled_at = "2026-06-23T12:00:00+00:00"

    response = client.post(
        "/jobs",
        json={
            "job_type": "echo",
            "queue_name": "critical",
            "priority": 10,
            "scheduled_at": scheduled_at,
        },
    )

    assert response.status_code == 201
    assert calls == [
            {
                "queue_name": "critical",
                "job_id": response.json()["id"],
                "priority": 10,
                "scheduled_at": datetime.fromisoformat(scheduled_at).replace(
                    tzinfo=None
                ),
            }
        ]


def test_create_job_rejects_invalid_input(client):
    response = client.post(
        "/jobs",
        json={"job_type": "", "queue_name": "", "max_attempts": 0},
    )

    assert response.status_code == 422
    error_locations = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "job_type") in error_locations
    assert ("body", "queue_name") in error_locations
    assert ("body", "max_attempts") in error_locations


def test_idempotency_key_returns_existing_job(client):
    payload = {
        "job_type": "echo",
        "payload": {"message": "hello"},
        "idempotency_key": "job-123",
    }

    first = client.post("/jobs", json=payload)
    second = client.post("/jobs", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_idempotency_key_keeps_original_job_payload(client):
    first = client.post(
        "/jobs",
        json={
            "job_type": "echo",
            "payload": {"message": "original"},
            "idempotency_key": "same-request",
        },
    )
    second = client.post(
        "/jobs",
        json={
            "job_type": "echo",
            "payload": {"message": "changed"},
            "idempotency_key": "same-request",
        },
    )

    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    response = client.get(f"/jobs/{first.json()['id']}")
    assert response.json()["payload"] == {"message": "original"}


def test_cancel_job(client):
    create_response = client.post("/jobs", json={"job_type": "echo"})
    job_id = create_response.json()["id"]

    response = client.post(f"/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


def test_cancel_missing_job_returns_404(client):
    response = client.post("/jobs/not-a-real-job/cancel")

    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


def test_get_missing_job_returns_404(client):
    response = client.get("/jobs/not-a-real-job")

    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


def test_cancel_succeeded_job_is_noop(client):
    create_response = client.post("/jobs", json={"job_type": "echo"})
    job_id = create_response.json()["id"]

    from app.worker.runtime import Worker

    assert Worker(worker_id="test-worker").run_once() is True

    response = client.post(f"/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_list_jobs_filters_by_status_and_queue(client):
    default_job = client.post("/jobs", json={"job_type": "echo"}).json()
    low_priority_job = client.post(
        "/jobs",
        json={"job_type": "echo", "queue_name": "slow", "priority": -1},
    ).json()
    client.post(f"/jobs/{default_job['id']}/cancel")

    canceled = client.get("/jobs", params={"status_filter": "canceled"})
    slow_queue = client.get("/jobs", params={"queue_name": "slow"})

    assert canceled.status_code == 200
    assert canceled.headers["X-Limit"] == "100"
    assert canceled.headers["X-Offset"] == "0"
    assert [job["id"] for job in canceled.json()] == [default_job["id"]]
    assert [job["id"] for job in slow_queue.json()] == [low_priority_job["id"]]
