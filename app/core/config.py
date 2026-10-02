from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    rabbitmq_url: str
    api_key: SecretStr

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50

    consumer_prefetch_count: int = 10
    webhook_timeout_seconds: float = 10.0
    gateway_min_delay_seconds: float = 2.0
    gateway_max_delay_seconds: float = 5.0
    gateway_success_rate: float = 0.9


@lru_cache
def get_settings() -> Settings:
    return Settings()