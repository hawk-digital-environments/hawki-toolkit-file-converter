from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker, WorkerTuner

from models import CallbackPayload, CallbackResult, JobStatus, ProcessResult

TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "file-converter")
TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "127.0.0.1:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
TEMPORAL_MAX_CONCURRENT = int(os.environ.get("TEMPORAL_MAX_CONCURRENT", "5"))
TEMPORAL_MAX_CACHED_WORKFLOWS = int(
    os.environ.get("TEMPORAL_MAX_CACHED_WORKFLOWS", "1000")
)  # 1000 is temporal default

SHARED_TMP = Path(os.getenv("SHARED_TMP_DIR", "/tmp/hawki-file-converter"))
ZIP_TTL_HOURS = float(os.getenv("ZIP_TTL_HOURS", "24"))
CALLBACK_TIMEOUT_SECONDS = float(os.getenv("CALLBACK_TIMEOUT_SECONDS", "30"))
PROCESS_FILE_TIMEOUT_MINUTES = float(os.getenv("PROCESS_FILE_TIMEOUT_MINUTES", "60"))


@activity.defn
async def process_file_activity(
    file_path: str,
    filename: str,
    result_dir: str,
) -> ProcessResult:
    from utils.processor import process_file_core

    file_bytes = Path(file_path).read_bytes()
    zip_bytes, headers = await process_file_core(file_bytes, filename)
    Path(result_dir).mkdir(parents=True, exist_ok=True)
    result_path = Path(result_dir) / "output.zip"
    result_path.write_bytes(zip_bytes)
    print(f"result_path={result_path} zip_size={len(zip_bytes)}")
    return ProcessResult(result_path=str(result_path), headers=headers)


@activity.defn
async def notify_callback_activity(url: str, payload: dict) -> CallbackResult:
    """POST a JSON payload to the caller-supplied callback URL.

    Retried by Temporal per the activity's retry policy. The payload always
    contains `job_id`, `status`, and a relative `download_url`.
    """
    import httpx

    async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    return CallbackResult(status_code=resp.status_code)


@activity.defn
async def cleanup_expired_zips_activity(shared_tmp: str, ttl_hours: float) -> list[str]:
    """Delete job directories under shared_tmp whose zip is older than ttl.

    Returns the list of job_ids (directory names) that were removed. The
    activity is invoked periodically by `CleanupExpiredZipsWorkflow` via a
    Temporal Schedule created at app startup.
    """
    cutoff_seconds = ttl_hours * 3600.0
    now = time.time()
    base = Path(shared_tmp)
    removed: list[str] = []
    if not base.exists():
        return removed
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        zip_path = entry / "result" / "output.zip"
        if not zip_path.exists():
            continue
        try:
            mtime = zip_path.stat().st_mtime
        except OSError:
            continue
        if now - mtime > cutoff_seconds:
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(entry.name)
    return removed


@workflow.defn
class ProcessFileWorkflow:
    def __init__(self) -> None:
        self.status: str = "queued"
        self.result_path: str | None = None
        self.headers: dict[str, str] = {}
        self.error_message: str | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None

    @workflow.run
    async def run(
        self,
        file_path: str,
        filename: str,
        result_dir: str,
        job_id: str | None = None,
        callback_url: str | None = None,
    ) -> ProcessResult:
        self.status = "running"
        self.started_at = workflow.now()
        try:
            result = await workflow.execute_activity(
                process_file_activity,
                args=[file_path, filename, result_dir],
                start_to_close_timeout=timedelta(minutes=PROCESS_FILE_TIMEOUT_MINUTES),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            self.result_path = result.result_path
            self.headers = result.headers

            if callback_url:
                download_url = f"/download/{job_id}" if job_id else None
                await workflow.execute_activity(
                    notify_callback_activity,
                    args=[
                        callback_url,
                        CallbackPayload(
                            job_id=job_id,
                            status="completed",
                            download_url=download_url,
                        ).model_dump(),
                    ],
                    start_to_close_timeout=timedelta(seconds=CALLBACK_TIMEOUT_SECONDS),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=2),
                        maximum_attempts=5,
                    ),
                )
            # Only mark completed once the callback (if any) has succeeded.
            self.status = "completed"
            return result
        except Exception as exc:
            self.status = "failed"
            root = exc
            while root.__cause__ is not None:
                root = root.__cause__
            self.error_message = str(root)
            raise
        finally:
            try:
                self.finished_at = workflow.now()
            except Exception:
                # Workflow event loop may be unavailable during shutdown.
                self.finished_at = self.started_at

    @workflow.query
    def get_status(self) -> JobStatus:
        def _iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return JobStatus(
            status=self.status,
            result_path=self.result_path,
            headers=self.headers,
            error_message=self.error_message,
            started_at=_iso(self.started_at),
            finished_at=_iso(self.finished_at),
        )


@workflow.defn
class CleanupExpiredZipsWorkflow:
    @workflow.run
    async def run(self, shared_tmp: str, ttl_hours: float) -> list[str]:
        return await workflow.execute_activity(
            cleanup_expired_zips_activity,
            args=[shared_tmp, ttl_hours],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


async def main() -> None:
    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)
    tuner = WorkerTuner.create_fixed(
        activity_slots=TEMPORAL_MAX_CONCURRENT,
    )
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        tuner=tuner,
        max_cached_workflows=TEMPORAL_MAX_CACHED_WORKFLOWS,
        workflows=[ProcessFileWorkflow, CleanupExpiredZipsWorkflow],
        activities=[
            process_file_activity,
            notify_callback_activity,
            cleanup_expired_zips_activity,
        ],
    )
    print(f"Worker started, polling task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
