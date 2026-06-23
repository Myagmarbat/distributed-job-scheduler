from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "distributed-job-scheduler"
    database_url: str = "sqlite:///./scheduler.db"
    queue_backend: str = "database"
    redis_url: str = "redis://localhost:6379/0"
    redis_dequeue_batch_size: int = 100
    worker_id: str = "worker-local"
    lease_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
