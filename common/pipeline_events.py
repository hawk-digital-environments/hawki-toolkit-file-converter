from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileDiscoveredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    job_id: UUID
    schema_version: str
    event_type: Literal["scrape.file.discovered"]
    source: str
    url: str
    page_url: str | None = None
    local_path: str
    relative_path: str
    filename: str
    extension: str
    content_type: str | None = None
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None
    discovered_at: datetime
    trace_id: str | None = None
    payload: dict[str, Any] | None = None


class DocumentConvertedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    job_id: UUID
    parent_event_id: UUID
    schema_version: str
    event_type: Literal["convert.document.completed"]
    source: Literal["file-converter"]
    original_url: str
    original_path: str
    original_relative_path: str | None = None
    converted_path: str
    converted_relative_path: str
    output_format: Literal["markdown"]
    converter_name: str
    converter_version: str | None = None
    input_checksum_sha256: str | None = None
    output_checksum_sha256: str | None = None
    converted_at: datetime
    trace_id: str | None = None
    payload: dict[str, Any] | None = None


class PipelineFailedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    job_id: UUID
    parent_event_id: UUID | None = None
    schema_version: str
    event_type: Literal["pipeline.failed"]
    failed_stage: Literal["file_conversion"]
    source: Literal["file-converter"]
    error_type: str
    error_message: str
    retry_count: int
    max_retries: int
    original_event_type: str
    original_event_payload: dict[str, Any]
    failed_at: datetime
    trace_id: str | None = None
