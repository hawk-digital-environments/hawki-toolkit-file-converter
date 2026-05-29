"""
File-to-Markdown converter service powered by kreuzberg.
"""

import os
import re
import kreuzberg

from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    Header,
    status,
    Form,
)
from pydantic import BaseModel

from utils.processor import process_file
from utils.logging_helper import logging_help
from utils.helper import get_supported_formats, get_file_type, get_image_file_formats
from pathlib import Path

app = FastAPI(title="File to Markdown Converter")
logger = logging_help()

REQUIRED_KEY = os.getenv("F_API_KEY", "").strip()
if not REQUIRED_KEY:
    raise RuntimeError("F_API_KEY not set! Server cannot run without it.")


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

    try:
        if not get_file_type(file.filename):
            unsuported_ext = Path(file.filename).suffix.lower()
            logger.error(f"Unsupported file type: {unsuported_ext}")
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type `{unsuported_ext}`. Supported types: {', '.join(sorted(get_supported_formats()))}"
            )
        return await process_file(file)
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.exception(f"Extraction failed for {repr(file.filename)}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Extraction failed for {repr(file.filename)}: {e}")
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
