from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from common.pipeline_events import (
    DocumentConvertedEvent,
    FileDiscoveredEvent,
    PipelineFailedEvent,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_file_discovered_event_validation() -> None:
    payload = {
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "schema_version": "1",
        "event_type": "scrape.file.discovered",
        "source": "scraper",
        "url": "https://example.com/a.pdf",
        "page_url": "https://example.com",
        "local_path": "/app/shared/input/a.pdf",
        "relative_path": "input/a.pdf",
        "filename": "a.pdf",
        "extension": ".pdf",
        "content_type": "application/pdf",
        "file_size_bytes": 100,
        "checksum_sha256": "abc",
        "discovered_at": _iso_now(),
        "trace_id": "trace-1",
        "payload": {"retry_count": 0},
    }

    event = FileDiscoveredEvent.model_validate(payload)
    assert event.event_type == "scrape.file.discovered"


def test_invalid_file_discovered_event_type_rejected() -> None:
    payload = {
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "schema_version": "1",
        "event_type": "bad.event",
        "source": "scraper",
        "url": "https://example.com/a.pdf",
        "local_path": "/app/shared/input/a.pdf",
        "relative_path": "input/a.pdf",
        "filename": "a.pdf",
        "extension": ".pdf",
        "discovered_at": _iso_now(),
    }

    with pytest.raises(ValidationError):
        FileDiscoveredEvent.model_validate(payload)


def test_document_converted_and_failed_events_validate() -> None:
    converted = DocumentConvertedEvent.model_validate(
        {
            "event_id": str(uuid4()),
            "job_id": str(uuid4()),
            "parent_event_id": str(uuid4()),
            "schema_version": "1",
            "event_type": "convert.document.completed",
            "source": "file-converter",
            "original_url": "https://example.com/a.pdf",
            "original_path": "/app/shared/input/a.pdf",
            "original_relative_path": "input/a.pdf",
            "converted_path": "/app/shared/converted/job/a.md",
            "converted_relative_path": "job/a.md",
            "output_format": "markdown",
            "converter_name": "file-converter",
            "converter_version": None,
            "input_checksum_sha256": "in",
            "output_checksum_sha256": "out",
            "converted_at": _iso_now(),
            "trace_id": "trace",
            "payload": {"duplicate": False},
        }
    )
    assert converted.event_type == "convert.document.completed"

    failed = PipelineFailedEvent.model_validate(
        {
            "event_id": str(uuid4()),
            "job_id": str(uuid4()),
            "parent_event_id": str(uuid4()),
            "schema_version": "1",
            "event_type": "pipeline.failed",
            "failed_stage": "file_conversion",
            "source": "file-converter",
            "error_type": "ValueError",
            "error_message": "bad",
            "retry_count": 3,
            "max_retries": 3,
            "original_event_type": "scrape.file.discovered",
            "original_event_payload": {"foo": "bar"},
            "failed_at": _iso_now(),
            "trace_id": None,
        }
    )
    assert failed.failed_stage == "file_conversion"
