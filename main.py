"""
File-to-Markdown converter service powered by kreuzberg.
"""

import asyncio
import os
import re
import shutil
import uuid

import kreuzberg
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Header,
    status,
)
from pathlib import Path
from pydantic import BaseModel
from prefect.deployments import run_deployment
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from utils.logging_helper import logging_help
from utils.helper import get_supported_formats, get_file_type, get_image_file_formats

app = FastAPI(title="File to Markdown Converter")
logger = logging_help()

REQUIRED_KEY = os.getenv("F_API_KEY", "").strip()
if not REQUIRED_KEY:
    raise RuntimeError("F_API_KEY not set! Server cannot run without it.")

DEPLOYMENT_NAME = "run-process-file/process-file"
SHARED_TMP = Path("/tmp/hawki-file-converter")


async def require_api_key(authorization: str | None = Header(default=None)):
    """Check that the required api key matches service key `REQUIRED_KEY`"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != REQUIRED_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


_SPECIAL_NAME_RE = re.compile(r"[^A-Za-z0-9._-]|\s")


class HealthCheck(BaseModel):
    status: str = "OK"


def _run_dependency_checks() -> None:
    """Check that expected ocr backend is installed"""
    if not "paddle-ocr" in kreuzberg.list_ocr_backends():
        raise RuntimeError("Missing binary: tesseract")


def _cleanup(fh, run_dir: str) -> None:
    fh.close()
    shutil.rmtree(run_dir, ignore_errors=True)


async def _run_processing(
    file_path: str, filename: str, result_dir: str
) -> dict:
    flow_run = await run_deployment(
        name=DEPLOYMENT_NAME,
        parameters={
            "file_path": file_path,
            "filename": filename,
            "result_dir": result_dir,
        },
    )
    result = flow_run.state.result()
    if asyncio.iscoroutine(result):
        result = await result
    return result


@app.post("/extract", dependencies=[Depends(require_api_key)])
async def extract(file: UploadFile = File(...)):
    """
    Extract content from uploaded file and convert to Markdown.

    Returns a ZIP file containing:
    - content_markdown.md: The converted markdown
    - images/: Directory with extracted images (if any)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    logger.info(
        f"Incoming upload: filename={repr(file.filename)}, "
        f"content_type={repr(getattr(file, 'content_type', None))}"
    )

    if _SPECIAL_NAME_RE.search(file.filename or ""):
        logger.warning(
            f"Filename contains spaces or special characters: {repr(file.filename)}"
        )

    if not get_file_type(file.filename):
        unsuported_ext = Path(file.filename).suffix.lower()
        logger.error(f"Unsupported file type: {unsuported_ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type `{unsuported_ext}`. Supported types: {', '.join(sorted(get_supported_formats()))}"
        )

    run_id = str(uuid.uuid4())
    run_dir = SHARED_TMP / run_id

    try:
        upload_path = run_dir / "upload" / (file.filename or "document")
        upload_path.parent.mkdir(parents=True)
        upload_path.write_bytes(await file.read())

        result_dir = run_dir / "result"
        result = await _run_processing(
            str(upload_path),
            file.filename or "document",
            str(result_dir),
        )

        result_path = Path(result["result_path"])
        fh = open(result_path, "rb")

        return StreamingResponse(
            content=fh,
            media_type="application/zip",
            headers=result["headers"],
            background=BackgroundTask(_cleanup, fh, str(run_dir)),
        )
    except HTTPException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    except RuntimeError as e:
        logger.exception(f"Extraction failed for {repr(file.filename)}: {e}")
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Extraction failed for {repr(file.filename)}: {e}")
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="conversion_failed")


@app.get("/", dependencies=[Depends(require_api_key)])
async def root():
    return {
        "service": "File to Markdown Converter",
        "auth": "Bearer token required",
        "supported_formats": get_supported_formats(),
        "image_formats": get_image_file_formats(),
        "endpoints": {
            "/extract": "POST - Upload file for conversion",
            "/": "GET - This info page",
        },
    }


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
