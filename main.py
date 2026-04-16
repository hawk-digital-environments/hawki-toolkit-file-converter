"""
File-to-Markdown converter service powered by kreuzberg.
"""

import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

import kreuzberg
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleState,
    WorkflowExecutionStatus,
)
from temporalio.service import RPCError, RPCStatusCode

from models import (
    ConvertResponse,
    JobDetailResponse,
    JobListResponse,
    JobStatus,
    JobSummary,
    ProcessResult,
    RootResponse,
)
from task import (
    SHARED_TMP,
    TASK_QUEUE,
    ZIP_TTL_HOURS,
    CleanupExpiredZipsWorkflow,
    ProcessFileWorkflow,
)
from utils.helper import (
    USE_TEXT_FALLBACK,
    get_file_type,
    get_image_file_formats,
    get_supported_formats,
    get_text_encoding,
    is_text_bytes,
    sanitize_filename,
)
from utils.logging_helper import logging_help

REQUIRED_KEY = os.getenv("F_API_KEY", "").strip()
if not REQUIRED_KEY:
    raise RuntimeError("F_API_KEY not set! Server cannot run without it.")

CLEANUP_SCHEDULE_ID = "ttl-cleanup-zips"

JobStatusFilter = StrEnum("JobStatusFilter", {m.name: m.name for m in WorkflowExecutionStatus})

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    global _temporal_client
    if _temporal_client is None:
        host = os.environ.get("TEMPORAL_HOST", "127.0.0.1:7233")
        namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
        _temporal_client = await Client.connect(host, namespace=namespace)
    return _temporal_client


security = HTTPBearer()


async def require_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Check that the required api key matches service key `REQUIRED_KEY`"""
    if credentials.credentials != REQUIRED_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class HealthCheck(BaseModel):
    status: str = "OK"


def _run_dependency_checks() -> None:
    """Check that expected ocr backend is installed"""
    if "paddle-ocr" not in kreuzberg.list_ocr_backends():
        raise RuntimeError("Missing binary: tesseract")


def _cleanup(fh, run_dir: str) -> None:
    fh.close()
    shutil.rmtree(run_dir, ignore_errors=True)


async def _prepare_upload(file: UploadFile) -> tuple[str, bytes, str | None]:
    """Validate and normalize an uploaded file.

    Shared by /extract and /convert. Returns
    `(safe_name, file_bytes, text_encoding_or_None)`. Raises HTTPException
    on validation failure.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    try:
        safe_name = sanitize_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_bytes = await file.read()

    text_encoding: str | None = None
    if not get_file_type(safe_name):
        if not USE_TEXT_FALLBACK:
            unsuported_ext = Path(safe_name).suffix.lower()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type `{unsuported_ext}`. Supported types: "
                f"{', '.join(sorted(get_supported_formats()))}",
            )
        if not is_text_bytes(file_bytes):
            unsuported_ext = Path(safe_name).suffix.lower()
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type `{unsuported_ext}`. Supported types: "
                f"{', '.join(sorted(get_supported_formats()))}",
            )
        text_encoding = get_text_encoding(file_bytes)
        if text_encoding is None:
            raise HTTPException(
                status_code=400,
                detail="Could not detect text encoding for the uploaded file.",
            )
    return safe_name, file_bytes, text_encoding


async def run_processing(
    file_path: str,
    filename: str,
    result_dir: str,
    *,
    text_encoding: str | None = None,
) -> ProcessResult:
    """Synchronously run the process workflow and return its result.

    Used by /extract. /convert uses `_start_conversion` instead.
    """
    client = await get_temporal_client()
    workflow_id = f"process-file-{uuid.uuid4()}"
    handle = await client.start_workflow(
        ProcessFileWorkflow.run,
        args=[file_path, filename, result_dir, text_encoding],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    try:
        return await handle.result()
    except Exception as exc:
        # Unwrap the root cause (ActivityError is wrapped by WorkflowFailureError;
        # the original RuntimeError at the bottom carries the user-facing message)
        root = exc
        while root.__cause__ is not None:
            root = root.__cause__
        raise RuntimeError(str(root)) from exc


async def _ensure_cleanup_schedule(client: Client) -> None:
    """Idempotently create the periodic zip-TTL-cleanup schedule."""
    try:
        await client.create_schedule(
            CLEANUP_SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    CleanupExpiredZipsWorkflow.run,
                    args=[str(SHARED_TMP), ZIP_TTL_HOURS],
                    id=f"{CLEANUP_SCHEDULE_ID}-run",
                    task_queue=TASK_QUEUE,
                ),
                spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=15))]),
                state=ScheduleState(paused=False, note="Periodic zip TTL sweep"),
            ),
        )
    except ScheduleAlreadyRunningError:
        pass
    except Exception as exc:
        logger.warning("Could not create cleanup schedule: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the periodic zip-TTL cleanup schedule on startup."""
    client = await get_temporal_client()
    await _ensure_cleanup_schedule(client)
    yield


app = FastAPI(
    title="File to Markdown Converter",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)
logger = logging_help()


@app.post("/extract", dependencies=[Depends(require_api_key)])
async def extract(file: UploadFile = File(...)):
    """
    Extract content from uploaded file and convert to Markdown.

    Returns a ZIP file containing:
    - content_markdown.md: The converted markdown
    - images/: Directory with extracted images (if any)
    """
    safe_name, file_bytes, text_encoding = await _prepare_upload(file)

    logger.info(
        f"Incoming upload: filename={repr(safe_name)}, "
        f"content_type={repr(getattr(file, 'content_type', None))}"
    )

    run_id = str(uuid.uuid4())
    run_dir = SHARED_TMP / run_id

    try:
        upload_path = run_dir / "upload" / safe_name
        upload_path.parent.mkdir(parents=True)
        upload_path.write_bytes(file_bytes)

        result_dir = run_dir / "result"
        result = await run_processing(
            str(upload_path),
            safe_name,
            str(result_dir),
            text_encoding=text_encoding,
        )

        result_path = Path(result.result_path)
        fh = open(result_path, "rb")

        return StreamingResponse(
            content=fh,
            media_type="application/zip",
            headers=result.headers,
            background=BackgroundTask(_cleanup, fh, str(run_dir)),
        )
    except HTTPException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    except RuntimeError as e:
        logger.exception(f"Extraction failed for {repr(safe_name)}: {e}")
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Extraction failed for {repr(safe_name)}: {e}")
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="conversion_failed")


@app.post(
    "/convert",
    response_model=ConvertResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
async def convert(
    file: UploadFile = File(...),
    callback_url: str | None = Form(default=None),
) -> ConvertResponse:
    """Asynchronously convert an uploaded file.

    Returns `202 Accepted` with `{job_id, status, download_url}` for the new job.
    """
    safe_name, file_bytes, text_encoding = await _prepare_upload(file)

    client = await get_temporal_client()

    job_id = f"convert-{uuid.uuid4()}"
    run_dir = SHARED_TMP / job_id

    try:
        upload_path = run_dir / "upload" / safe_name
        upload_path.parent.mkdir(parents=True)
        upload_path.write_bytes(file_bytes)

        result_dir = run_dir / "result"
        await client.start_workflow(
            ProcessFileWorkflow.run,
            args=[
                str(upload_path),
                safe_name,
                str(result_dir),
                text_encoding,
                job_id,
                callback_url,
            ],
            id=job_id,
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        logger.exception("Failed to start conversion workflow: %s", exc)
        raise HTTPException(status_code=500, detail="conversion_failed") from exc

    return ConvertResponse(
        job_id=job_id,
        status="queued",
        download_url=f"/download/{job_id}",
    )


def job_zip_path(job_id: str) -> Path:
    return SHARED_TMP / job_id / "result" / "output.zip"


def _touch(path: Path) -> None:
    """Update mtime on the zip so the TTL sweeper treats it as freshly accessed."""
    try:
        import os as _os

        _os.utime(path, None)
    except OSError:
        pass


async def _query_job_status(client: Client, job_id: str) -> JobStatus | None:
    """Return our custom workflow status dict, or None if the workflow is gone."""
    handle = client.get_workflow_handle(job_id)
    try:
        return await handle.query(ProcessFileWorkflow.get_status)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="job_not_found")
        if exc.status == RPCStatusCode.INVALID_ARGUMENT:
            return None
        raise


@app.get("/download/{job_id}", dependencies=[Depends(require_api_key)])
async def download(job_id: str):
    """Download the result zip for a job.

    - 409 if the job is still running.
    - 410 Gone if the job failed, the zip expired (post-TTL), or the job is unknown.
    - 200 with application/zip stream otherwise. Re-downloadable until TTL.

    Note: Returns 404 once Temporal purges the workflow record (per
    `DEFAULT_NAMESPACE_RETENTION`). `ZIP_TTL_HOURS` must be set <= retention;
    otherwise the zip will outlive its workflow record and become unreachable.
    """
    client = await get_temporal_client()
    job_status = await _query_job_status(client, job_id)
    if job_status is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    state = job_status.status
    if state in ("queued", "running"):
        raise HTTPException(status_code=409, detail="job_still_running")
    if state == "failed":
        raise HTTPException(
            status_code=410,
            detail=job_status.error_message or "job_failed",
        )
    if state != "completed":
        raise HTTPException(status_code=409, detail=f"job_state_{state}")

    zip_path = job_zip_path(job_id)
    if not zip_path.exists():
        raise HTTPException(status_code=410, detail="result_expired_or_missing")

    fh = open(zip_path, "rb")
    headers = dict(job_status.headers or {})

    return StreamingResponse(
        content=fh,
        media_type="application/zip",
        headers=headers,
        background=BackgroundTask(_touch, zip_path),
    )


def workflow_to_summary(row) -> JobSummary:
    """Raw passthrough of Temporal workflow execution fields."""
    sa = {p.key.name: p.value for p in row.typed_search_attributes}
    return JobSummary(
        job_id=row.id,
        run_id=row.run_id,
        workflow_type=row.workflow_type,
        task_queue=row.task_queue,
        status=row.status.name if row.status else None,
        start_time=row.start_time.isoformat() if row.start_time else None,
        execution_time=row.execution_time.isoformat() if row.execution_time else None,
        close_time=row.close_time.isoformat() if row.close_time else None,
        history_length=row.history_length,
        search_attributes=sa,
    )


@app.get("/jobs", response_model=JobListResponse, dependencies=[Depends(require_api_key)])
async def list_jobs(
    status: JobStatusFilter | None = None,
    limit: int = 100,
) -> JobListResponse:
    """List converter workflows currently visible to Temporal (raw passthrough).

    Filters by the `ProcessFileWorkflow` type so unrelated workflows (e.g.
    cleanup runs) don't appear here. Optional `?status=` narrows by
    ExecutionStatus (applied client-side for compatibility with visibility
    backends that ignore the server-side predicate).

    Note: Only jobs still within Temporal's `DEFAULT_NAMESPACE_RETENTION`
    window (default 24h) appear here. Jobs older than retention are purged
    from Temporal and will not show up even if their zip is still on disk.
    """
    client = await get_temporal_client()
    base_query = "WorkflowType = 'ProcessFileWorkflow'"
    desired = status.name if status else None

    rows = []
    async for row in client.list_workflows(query=base_query, limit=limit):
        status_name = row.status.name if row.status else None
        if desired is not None and status_name != desired:
            continue
        rows.append(workflow_to_summary(row))
    return JobListResponse(jobs=rows, count=len(rows))


@app.get(
    "/jobs/{job_id}",
    response_model=JobDetailResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_job(job_id: str) -> JobDetailResponse:
    """Detail a single job: raw Temporal describe + our workflow status query.

    Returns 404 once Temporal purges the workflow record (per
    `DEFAULT_NAMESPACE_RETENTION`), even if a result zip still exists on disk.
    """
    client = await get_temporal_client()
    handle = client.get_workflow_handle(job_id)
    try:
        desc = await handle.describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail="job_not_found")
        raise

    base = workflow_to_summary(desc)
    job_status = await _query_job_status(client, job_id)
    return JobDetailResponse(**base.model_dump(), status_detail=job_status)


@app.get("/", response_model=RootResponse, dependencies=[Depends(require_api_key)])
async def root() -> RootResponse:
    version = Path("VERSION.md")
    return RootResponse(
        version=version.read_text().strip(),
        service="File to Markdown Converter",
        auth="Bearer token required",
        supported_formats=get_supported_formats(),
        image_formats=get_image_file_formats(),
        text_fallback=USE_TEXT_FALLBACK,
        endpoints={
            "/extract": "POST - Synchronous upload + conversion (returns zip)",
            "/convert": "POST - Async conversion; returns job_id (optional callback_url)",
            "/download/{job_id}": "GET - Download the result zip for a job",
            "/jobs": "GET - List workflows (raw Temporal passthrough, ?status= filter)",
            "/jobs/{job_id}": "GET - Detail a single job",
            "/": "GET - This info page",
        },
    )


@app.get(
    "/health",
    tags=["healthcheck"],
    summary="Health check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
async def healthcheck() -> HealthCheck:
    try:
        _run_dependency_checks()
    except Exception as exc:
        logger.exception("Health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="unhealthy",
        ) from exc

    return HealthCheck(status="OK")
