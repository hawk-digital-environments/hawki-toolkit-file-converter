from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class CommunicationSettings:
    communication_enabled: bool = _as_bool(os.getenv("COMMUNICATION_ENABLED"), False)
    communication_method: str = os.getenv("COMMUNICATION_METHOD", "none")

    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port: int = _as_int(os.getenv("RABBITMQ_PORT"), 5672)
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "guest")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "guest")
    rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST", "/")
    rabbitmq_heartbeat: int = _as_int(os.getenv("RABBITMQ_HEARTBEAT"), 30)
    rabbitmq_connection_timeout: int = _as_int(os.getenv("RABBITMQ_CONNECTION_TIMEOUT"), 30)

    events_exchange: str = os.getenv("RABBITMQ_EVENTS_EXCHANGE", "pipeline.events")
    events_exchange_type: str = os.getenv("RABBITMQ_EVENTS_EXCHANGE_TYPE", "direct")

    retry_exchange: str = os.getenv("RABBITMQ_RETRY_EXCHANGE", "pipeline.retry")
    retry_exchange_type: str = os.getenv("RABBITMQ_RETRY_EXCHANGE_TYPE", "direct")

    failed_exchange: str = os.getenv("RABBITMQ_FAILED_EXCHANGE", "pipeline.failed")
    failed_exchange_type: str = os.getenv("RABBITMQ_FAILED_EXCHANGE_TYPE", "direct")

    file_conversion_queue: str = os.getenv("RABBITMQ_FILE_CONVERSION_QUEUE", "file_conversion_jobs")
    file_discovered_routing_key: str = os.getenv("RABBITMQ_FILE_DISCOVERED_ROUTING_KEY", "scrape.file.discovered")

    file_conversion_retry_queue: str = os.getenv("RABBITMQ_FILE_CONVERSION_RETRY_QUEUE", "file_conversion_jobs_retry")
    file_conversion_retry_routing_key: str = os.getenv(
        "RABBITMQ_FILE_CONVERSION_RETRY_ROUTING_KEY",
        "scrape.file.discovered.retry",
    )

    document_converted_routing_key: str = os.getenv(
        "RABBITMQ_DOCUMENT_CONVERTED_ROUTING_KEY",
        "convert.document.completed",
    )

    failed_queue: str = os.getenv("RABBITMQ_FAILED_QUEUE", "failed_jobs")
    failed_routing_key: str = os.getenv("RABBITMQ_FAILED_ROUTING_KEY", "pipeline.failed")

    retry_delay_ms: int = _as_int(os.getenv("RABBITMQ_RETRY_DELAY_MS"), 5000)
    prefetch_count: int = _as_int(os.getenv("RABBITMQ_PREFETCH_COUNT"), 1)
    max_retries: int = _as_int(os.getenv("RABBITMQ_MAX_RETRIES"), 3)
    queue_type: str = os.getenv("RABBITMQ_QUEUE_TYPE", "quorum")

    publisher_confirms: bool = _as_bool(os.getenv("RABBITMQ_PUBLISHER_CONFIRMS"), True)
    persistent_messages: bool = _as_bool(os.getenv("RABBITMQ_PERSISTENT_MESSAGES"), True)

    job_schema_version: str = os.getenv("JOB_SCHEMA_VERSION", "1")
    service_name: str = os.getenv("SERVICE_NAME", "file-converter")

    shared_storage_root: str = os.getenv("SHARED_STORAGE_ROOT", "/app/shared")
    converted_output_root: str = os.getenv("CONVERTED_OUTPUT_ROOT", "/app/shared/converted")

    def amqp_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost.lstrip('/')}"
        )


SETTINGS = CommunicationSettings()
