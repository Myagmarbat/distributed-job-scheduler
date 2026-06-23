from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime


class JobQueue(ABC):
    @abstractmethod
    def enqueue(
        self,
        queue_name: str,
        job_id: str,
        *,
        priority: int = 0,
        scheduled_at: datetime | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def dequeue(self, queue_names: Iterable[str]) -> str | None:
        raise NotImplementedError
