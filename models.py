from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConvertResponse(BaseModel):
    job_id: str
    status: Literal["reused", "queued"]
    download_url: str


class ProcessResult(BaseModel):
    result_path: str
    headers: dict[str, str]


class CallbackResult(BaseModel):
    status_code: int


class CallbackPayload(BaseModel):
    job_id: str | None
    status: str
    download_url: str | None


class JobStatus(BaseModel):
    status: str
    result_path: str | None
    headers: dict[str, str]
    error_message: str | None
    started_at: str | None
    finished_at: str | None


class JobSummary(BaseModel):
    job_id: str
    run_id: str
    workflow_type: str
    task_queue: str
    status: str | None
    start_time: str | None
    execution_time: str | None
    close_time: str | None
    history_length: int
    search_attributes: dict[str, Any]


class JobListResponse(BaseModel):
    jobs: list[JobSummary]
    count: int


class JobDetailResponse(JobSummary):
    status_detail: JobStatus | None = None


class RootResponse(BaseModel):
    version: str
    service: str
    auth: str
    supported_formats: set[str]
    image_formats: set[str]
    text_fallback: bool = Field(
        description="Any file with decodable text content not matching a supported format is treated as plain text"
    )
    endpoints: dict[str, str]
