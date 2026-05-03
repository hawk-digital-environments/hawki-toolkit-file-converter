from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from aio_pika import IncomingMessage
from fastapi import UploadFile
from pydantic import ValidationError

from common.pipeline_events import (
    DocumentConvertedEvent,
    FileDiscoveredEvent,
    PipelineFailedEvent,
)
from rabbitmq.client import RabbitMQClient
from rabbitmq.settings import CommunicationSettings, SETTINGS
from workers.failure_classifier import (
    EmptyOutputError,
    FailureCategory,
    InvalidSchemaError,
    MissingLocalFileError,
    UnsupportedFileTypeError,
    UnsafePathError,
    classify_failure,
)

logger = logging.getLogger("file_conversion_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_word_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in {".doc", ".docx"}


def _sanitize_relative_path(relative_path: str, fallback_filename: str) -> Path:
    original = Path(relative_path) if relative_path else Path(fallback_filename)
    safe_parts = [part for part in original.parts if part not in {"", ".", ".."}]
    if not safe_parts:
        safe_parts = [fallback_filename]

    safe_relative = Path(*safe_parts)
    if safe_relative.suffix:
        return safe_relative.with_suffix(".md")
    return safe_relative / "converted.md"


def _read_retry_count(event_payload: dict[str, Any]) -> int:
    payload = event_payload.get("payload") or {}
    retry_count = payload.get("retry_count", 0)
    try:
        return int(retry_count)
    except (TypeError, ValueError):
        return 0


def _set_retry_count(event_payload: dict[str, Any], retry_count: int) -> dict[str, Any]:
    enriched = deepcopy(event_payload)
    payload = enriched.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"original_payload": payload}
    payload["retry_count"] = retry_count
    enriched["payload"] = payload
    return enriched


def validate_local_path(local_path: str, shared_storage_root: Path) -> Path:
    root_resolved = shared_storage_root.resolve()
    candidate = Path(local_path)
    if not candidate.is_absolute():
        candidate = root_resolved / candidate

    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as error:
        raise UnsafePathError(f"Path outside allowed root: {resolved}") from error

    if not resolved.exists() or not resolved.is_file():
        raise MissingLocalFileError(f"Missing local file: {resolved}")

    return resolved


async def _read_streaming_response_bytes(response: Any) -> bytes:
    if hasattr(response, "body") and response.body is not None:
        return response.body

    if not hasattr(response, "body_iterator"):
        raise ValueError("Unsupported response type from converter")

    body = bytearray()
    async for chunk in response.body_iterator:
        body.extend(chunk)
    return bytes(body)


async def convert_to_markdown_with_existing_logic(input_path: Path) -> str:
    from utils.pdf_processor import process_pdf
    from utils.word_processor import process_word

    data = input_path.read_bytes()
    upload_file = UploadFile(filename=input_path.name, file=io.BytesIO(data))

    if input_path.suffix.lower() == ".pdf":
        response = await process_pdf(upload_file, chunkable=True)
    elif _is_word_file(input_path.name):
        response = await process_word(upload_file)
    else:
        raise UnsupportedFileTypeError(f"Unsupported file type: {input_path.suffix.lower()}")

    zip_bytes = await _read_streaming_response_bytes(response)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        markdown_path = "output/content_markdown.md"
        if markdown_path not in archive.namelist():
            raise EmptyOutputError("Markdown output missing in conversion archive")

        markdown_text = archive.read(markdown_path).decode("utf-8", errors="replace")

    if not markdown_text.strip():
        raise EmptyOutputError("Conversion output is empty")

    return markdown_text


class FileConversionWorker:
    def __init__(
        self,
        rabbitmq_client: RabbitMQClient | None = None,
        settings: CommunicationSettings = SETTINGS,
    ) -> None:
        self.settings = settings
        self.rabbit = rabbitmq_client or RabbitMQClient(settings)
        self.shared_storage_root = Path(settings.shared_storage_root)
        self.converted_output_root = Path(settings.converted_output_root)
        self.converted_output_root.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        await self.rabbit.connect()
        assert self.rabbit.topology is not None
        await self.rabbit.topology.file_conversion_queue.consume(
            self.handle_message,
            no_ack=False,
        )
        logger.info("File conversion worker started and consuming queue")
        await asyncio.Future()

    async def handle_message(self, message: IncomingMessage) -> None:
        raw_body = message.body.decode("utf-8", errors="replace")
        try:
            event_payload = json.loads(raw_body)
            event = FileDiscoveredEvent.model_validate(event_payload)

            converted_event = await self._process_file_discovered_event(event)
            await self.rabbit.publish_event(
                converted_event,
                routing_key=self.settings.document_converted_routing_key,
            )
            await message.ack()
            logger.info("Processed event job_id=%s event_id=%s", event.job_id, event.event_id)
        except Exception as error:
            await self._handle_failure(message=message, raw_body=raw_body, error=error)

    async def _handle_failure(
        self,
        message: IncomingMessage,
        raw_body: str,
        error: Exception,
    ) -> None:
        try:
            event_payload = json.loads(raw_body)
        except json.JSONDecodeError:
            event_payload = {"raw_payload": raw_body}

        retry_count = _read_retry_count(event_payload)
        category = classify_failure(error)

        if category == FailureCategory.TRANSIENT:
            next_retry_count = retry_count + 1
            if next_retry_count <= self.settings.max_retries:
                retry_event = _set_retry_count(event_payload, next_retry_count)
                await self.rabbit.publish_retry(retry_event)
                await message.ack()
                logger.warning(
                    "Transient failure. Republished to retry queue retry_count=%s error=%s",
                    next_retry_count,
                    error,
                )
                return

        failed_event = self._build_failed_event(event_payload, error=error, retry_count=retry_count)
        await self.rabbit.publish_failed_event(failed_event)
        await message.ack()
        logger.error("Message failed permanently error=%s", error)

    async def _process_file_discovered_event(
        self,
        event: FileDiscoveredEvent,
    ) -> DocumentConvertedEvent:
        input_path = validate_local_path(event.local_path, self.shared_storage_root)

        extension = (event.extension or input_path.suffix).lower()
        if not extension.startswith("."):
            extension = f".{extension}"

        if extension not in {".pdf", ".doc", ".docx"} and not _is_word_file(input_path.name):
            raise UnsupportedFileTypeError(f"Unsupported file type: {extension}")

        input_checksum = event.checksum_sha256 or sha256_file(input_path)

        job_output_dir = self.converted_output_root / str(event.job_id)
        safe_relative_md = _sanitize_relative_path(event.relative_path, event.filename)
        output_path = job_output_dir / safe_relative_md
        output_path.parent.mkdir(parents=True, exist_ok=True)

        meta_path = job_output_dir / "conversion_meta.json"
        record_key = str(safe_relative_md)

        metadata = self._load_metadata(meta_path, event.job_id)
        existing_record = metadata["records"].get(record_key, {})

        is_duplicate = (
            output_path.exists()
            and existing_record.get("status") == "completed"
            and existing_record.get("input_checksum") == input_checksum
        )

        if is_duplicate:
            output_checksum = existing_record.get("output_checksum") or sha256_file(output_path)
            return self._build_converted_event(
                event=event,
                output_path=output_path,
                output_checksum=output_checksum,
                input_checksum=input_checksum,
                duplicate=True,
            )

        metadata["records"][record_key] = {
            "job_id": str(event.job_id),
            "source_event_id": str(event.event_id),
            "input_path": str(input_path),
            "input_checksum": input_checksum,
            "output_path": str(output_path),
            "output_checksum": None,
            "status": "processing",
            "created_at": utcnow().isoformat(),
            "completed_at": None,
            "error": None,
        }
        self._save_metadata(meta_path, metadata)

        try:
            markdown = await convert_to_markdown_with_existing_logic(input_path)
            output_path.write_text(markdown, encoding="utf-8")

            output_checksum = sha256_file(output_path)
            metadata["records"][record_key].update(
                {
                    "output_checksum": output_checksum,
                    "status": "completed",
                    "completed_at": utcnow().isoformat(),
                    "error": None,
                }
            )
            self._save_metadata(meta_path, metadata)

            return self._build_converted_event(
                event=event,
                output_path=output_path,
                output_checksum=output_checksum,
                input_checksum=input_checksum,
                duplicate=False,
            )
        except Exception as error:
            metadata["records"][record_key].update(
                {
                    "status": "failed",
                    "completed_at": utcnow().isoformat(),
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
            )
            self._save_metadata(meta_path, metadata)
            if isinstance(error, ValidationError):
                raise InvalidSchemaError(str(error)) from error
            raise

    def _build_converted_event(
        self,
        event: FileDiscoveredEvent,
        output_path: Path,
        output_checksum: str,
        input_checksum: str,
        duplicate: bool,
    ) -> DocumentConvertedEvent:
        converted_relative = output_path.relative_to(self.converted_output_root)

        payload = event.payload or {}
        if not isinstance(payload, dict):
            payload = {"original_payload": payload}
        payload = {**payload, "duplicate": duplicate}

        return DocumentConvertedEvent(
            event_id=uuid4(),
            job_id=event.job_id,
            parent_event_id=event.event_id,
            schema_version=self.settings.job_schema_version,
            event_type="convert.document.completed",
            source="file-converter",
            original_url=event.url,
            original_path=event.local_path,
            original_relative_path=event.relative_path,
            converted_path=str(output_path),
            converted_relative_path=str(converted_relative),
            output_format="markdown",
            converter_name=self.settings.service_name,
            converter_version=None,
            input_checksum_sha256=input_checksum,
            output_checksum_sha256=output_checksum,
            converted_at=utcnow(),
            trace_id=event.trace_id,
            payload=payload,
        )

    def _build_failed_event(
        self,
        event_payload: dict[str, Any],
        error: Exception,
        retry_count: int,
    ) -> PipelineFailedEvent:
        parent_event_id: UUID | None = None
        job_id: UUID = uuid4()
        original_event_type = str(event_payload.get("event_type", "unknown"))
        trace_id = event_payload.get("trace_id")

        raw_job_id = event_payload.get("job_id")
        if raw_job_id:
            try:
                job_id = UUID(str(raw_job_id))
            except ValueError:
                pass

        raw_parent_event_id = event_payload.get("event_id")
        if raw_parent_event_id:
            try:
                parent_event_id = UUID(str(raw_parent_event_id))
            except ValueError:
                parent_event_id = None

        return PipelineFailedEvent(
            event_id=uuid4(),
            job_id=job_id,
            parent_event_id=parent_event_id,
            schema_version=self.settings.job_schema_version,
            event_type="pipeline.failed",
            failed_stage="file_conversion",
            source="file-converter",
            error_type=type(error).__name__,
            error_message=str(error),
            retry_count=retry_count,
            max_retries=self.settings.max_retries,
            original_event_type=original_event_type,
            original_event_payload=event_payload,
            failed_at=utcnow(),
            trace_id=trace_id,
        )

    def _load_metadata(self, meta_path: Path, job_id: UUID) -> dict[str, Any]:
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("records"), dict):
                    return data
            except json.JSONDecodeError:
                logger.warning("Invalid metadata file, recreating: %s", meta_path)

        return {
            "job_id": str(job_id),
            "records": {},
        }

    def _save_metadata(self, meta_path: Path, metadata: dict[str, Any]) -> None:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


async def _run_worker() -> None:
    if not SETTINGS.communication_enabled or SETTINGS.communication_method != "rabbitmq":
        raise RuntimeError(
            "Worker communication is disabled. Set COMMUNICATION_ENABLED=true and "
            "COMMUNICATION_METHOD=rabbitmq."
        )

    worker = FileConversionWorker()
    await worker.start()


def main() -> None:
    asyncio.run(_run_worker())


if __name__ == "__main__":
    main()
