from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from rabbitmq.settings import CommunicationSettings
from workers.failure_classifier import UnsupportedFileTypeError
from workers.file_conversion_worker import FileConversionWorker, sha256_file


class FakeRabbitClient:
    def __init__(self) -> None:
        self.published_events: list[tuple[object, str]] = []
        self.retry_events: list[object] = []
        self.failed_events: list[object] = []

    async def publish_event(self, event, routing_key: str) -> None:
        self.published_events.append((event, routing_key))

    async def publish_retry(self, event) -> None:
        self.retry_events.append(event)

    async def publish_failed_event(self, event) -> None:
        self.failed_events.append(event)


class FakeMessage:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.acked = False

    async def ack(self) -> None:
        self.acked = True


def _event_payload(local_path: str, relative_path: str = "docs/input.pdf") -> dict:
    return {
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "schema_version": "1",
        "event_type": "scrape.file.discovered",
        "source": "scraper",
        "url": "https://example.com/file.pdf",
        "page_url": "https://example.com",
        "local_path": local_path,
        "relative_path": relative_path,
        "filename": "input.pdf",
        "extension": ".pdf",
        "content_type": "application/pdf",
        "file_size_bytes": 10,
        "checksum_sha256": None,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": "trace-1",
        "payload": {},
    }


def test_worker_successful_flow(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    converted = tmp_path / "converted"
    source = shared / "docs" / "input.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf")

    settings = CommunicationSettings(
        shared_storage_root=str(shared),
        converted_output_root=str(converted),
        max_retries=3,
    )
    rabbit = FakeRabbitClient()
    worker = FileConversionWorker(rabbitmq_client=rabbit, settings=settings)

    payload = _event_payload(str(source))
    message = FakeMessage(payload)

    with patch(
        "workers.file_conversion_worker.convert_to_markdown_with_existing_logic",
        AsyncMock(return_value="# Converted"),
    ):
        asyncio.run(worker.handle_message(message))

    assert message.acked is True
    assert len(rabbit.published_events) == 1
    converted_event, routing_key = rabbit.published_events[0]
    assert routing_key == "convert.document.completed"
    assert converted_event.output_format == "markdown"
    assert Path(converted_event.converted_path).exists()


def test_worker_retries_transient_failures(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    converted = tmp_path / "converted"
    source = shared / "docs" / "input.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf")

    settings = CommunicationSettings(
        shared_storage_root=str(shared),
        converted_output_root=str(converted),
        max_retries=3,
    )
    rabbit = FakeRabbitClient()
    worker = FileConversionWorker(rabbitmq_client=rabbit, settings=settings)

    payload = _event_payload(str(source))
    message = FakeMessage(payload)

    with patch(
        "workers.file_conversion_worker.convert_to_markdown_with_existing_logic",
        AsyncMock(side_effect=TimeoutError("temporary timeout")),
    ):
        asyncio.run(worker.handle_message(message))

    assert message.acked is True
    assert len(rabbit.retry_events) == 1
    retry_payload = rabbit.retry_events[0]
    assert retry_payload["payload"]["retry_count"] == 1
    assert len(rabbit.failed_events) == 0


def test_worker_sends_failed_event_on_permanent_failure(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    converted = tmp_path / "converted"
    source = shared / "docs" / "input.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf")

    settings = CommunicationSettings(
        shared_storage_root=str(shared),
        converted_output_root=str(converted),
        max_retries=3,
    )
    rabbit = FakeRabbitClient()
    worker = FileConversionWorker(rabbitmq_client=rabbit, settings=settings)

    payload = _event_payload(str(source))
    message = FakeMessage(payload)

    with patch(
        "workers.file_conversion_worker.convert_to_markdown_with_existing_logic",
        AsyncMock(side_effect=UnsupportedFileTypeError("unsupported")),
    ):
        asyncio.run(worker.handle_message(message))

    assert message.acked is True
    assert len(rabbit.retry_events) == 0
    assert len(rabbit.failed_events) == 1
    assert rabbit.failed_events[0].event_type == "pipeline.failed"


def test_worker_duplicate_event_uses_idempotency(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    converted = tmp_path / "converted"
    source = shared / "docs" / "input.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf")

    settings = CommunicationSettings(
        shared_storage_root=str(shared),
        converted_output_root=str(converted),
        max_retries=3,
    )
    rabbit = FakeRabbitClient()
    worker = FileConversionWorker(rabbitmq_client=rabbit, settings=settings)

    payload = _event_payload(str(source))

    convert_mock = AsyncMock(return_value="# Converted")
    with patch("workers.file_conversion_worker.convert_to_markdown_with_existing_logic", convert_mock):
        first_message = FakeMessage(payload)
        asyncio.run(worker.handle_message(first_message))

        second_message = FakeMessage(payload)
        asyncio.run(worker.handle_message(second_message))

    assert first_message.acked is True
    assert second_message.acked is True
    assert convert_mock.await_count == 1
    assert len(rabbit.published_events) == 2

    first_event, _ = rabbit.published_events[0]
    second_event, _ = rabbit.published_events[1]
    assert first_event.input_checksum_sha256 == second_event.input_checksum_sha256

    converted_path = Path(first_event.converted_path)
    assert converted_path.exists()
    assert first_event.output_checksum_sha256 == sha256_file(converted_path)
