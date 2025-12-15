#!/usr/bin/env python3
"""
File-to-Markdown converter service.

Supports:
- PDF files (using pyMuPDF)
- Word documents (.doc, .docx using pypandoc)
"""

import importlib.util
import shutil
from pathlib import Path
import re, os

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, status
from pydantic import BaseModel

from utils.pdf_processor import process_pdf
from utils.word_processor import process_word, is_word_file
from utils.logging_helper import logging_help  

app = FastAPI(title="File → Markdown Converter")
# Logger initialization
logger = logging_help()
################# API KEY VALIDATION ####################
REQUIRED_KEY = os.getenv("F_API_KEY", "").strip()
if not REQUIRED_KEY:
    raise RuntimeError("F_API_KEY not set! Server cannot run without it.")

async def require_api_key(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    # token logging removed to avoid leaking secrets
    if token != REQUIRED_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

#####################

# any special codes can be detected here outside the normal scope > good for finding Deutsch words that cause issues
_SPECIAL_NAME_RE = re.compile(r"[^A-Za-z0-9._-]|\s")


class HealthCheck(BaseModel):
    """Simple health response model."""

    status: str = "OK"


def _run_dependency_checks() -> None:
    """
    Ensure critical runtime dependencies are present.

    Raises:
        RuntimeError: If required binaries or modules are missing.
    """
    missing_modules = [
        module for module in ("fitz", "pypandoc") if importlib.util.find_spec(module) is None
    ]
    if missing_modules:
        raise RuntimeError(f"Missing Python modules: {', '.join(missing_modules)}")

    missing_binaries = [
        binary for binary in ("tesseract", "pandoc") if shutil.which(binary) is None
    ]
    if missing_binaries:
        raise RuntimeError(f"Missing binaries: {', '.join(missing_binaries)}")


def get_file_type(filename: str) -> str:
    """Determine file type from filename."""
    if not filename:
        return "unknown"
    
    ext = Path(filename).suffix.lower()
    
    if ext == '.pdf':
        return "pdf"
    elif ext in ['.doc', '.docx']:
        return "word"
    else:
        return "unknown"


@app.post("/extract", dependencies=[Depends(require_api_key)])
async def extract(
    file: UploadFile = File(...),
    chunkable: bool = True
):
    """
    Extract content from uploaded file and convert to Markdown.
    
    Supports:
    - PDF files (with optional chunking)
    - Word documents (.doc, .docx)
    
    Returns a ZIP file containing:
    - content_markdown.md: The converted markdown
    - images_*/: Directory with extracted images
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Log the incoming filename and content type
    logger.info(f"Incoming upload: filename={repr(file.filename)}, content_type={repr(getattr(file, 'content_type', None))}")

    # this line warns us if filename contains spaces or special characters
    if _SPECIAL_NAME_RE.search(file.filename or ""):
        logger.warning(f"Filename contains spaces or special characters: {repr(file.filename)}")

    file_type = get_file_type(file.filename)
    logger.info(f"Detected file type: {file_type} (chunkable={chunkable})")

    try:
        if file_type == "pdf":
            logger.info("Selected processor: PDF")
            # process_pdf  returns a ZIP with markdown/images
            return await process_pdf(file, chunkable)
        elif file_type == "word":
            logger.info("Selected processor: Word")
            return await process_word(file)
        else:
            supported_types = ['.pdf', '.doc', '.docx']
            logger.error(f"Unsupported file type: {Path(file.filename).suffix.lower()}")
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type. Supported types: {', '.join(supported_types)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        # other unexpected error is logged here as 500
        logger.exception(f"Extraction failed for {repr(file.filename)}: {e}")
        raise HTTPException(status_code=500, detail="conversion_failed")


@app.get("/", dependencies=[Depends(require_api_key)])
async def root():
    """Health check and service info."""
    return {
        "service": "File to Markdown Converter",
        "auth": "X-API-KEY required",
        "supported_formats": [".pdf", ".doc", ".docx"],
        "endpoints": {
            "/extract": "POST - Upload file for conversion",
            "/": "GET - This info page"
        }
    }


@app.get(
    "/health",
    tags=["healthcheck"],
    summary="QUICK health check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
async def healthcheck() -> HealthCheck:
    """
    Returns 200 when core dependencies are available; otherwise 500.
    """
    try:
        _run_dependency_checks()
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="unhealthy",
        ) from exc

    return HealthCheck(status="OK")
