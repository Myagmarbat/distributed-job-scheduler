from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=120)
    queue_name: str = Field(default="default", min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None
    priority: int = 0
    max_attempts: int = Field(default=3, ge=1, le=100)
    idempotency_key: str | None = Field(default=None, max_length=160)


class JobOut(BaseModel):
    id: str
    queue_name: str
    job_type: str
    payload: dict[str, Any]
    status: str
    priority: int
    max_attempts: int
    attempt_count: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    idempotency_key: str | None

    model_config = {"from_attributes": True}


class JobCreated(BaseModel):
    id: str
    status: str
