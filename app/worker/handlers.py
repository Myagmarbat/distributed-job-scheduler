from collections.abc import Callable
from typing import Any

JobHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise LookupError(f"no handler registered for job_type={job_type}") from exc


registry = HandlerRegistry()


def echo_handler(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": payload}


registry.register("echo", echo_handler)
