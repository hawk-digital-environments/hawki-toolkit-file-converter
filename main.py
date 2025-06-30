#!/usr/bin/env python3
"""
File-to-Markdown converter service.

Supports:
- PDF files (using pyMuPDF)
- Word documents (.doc, .docx using pypandoc)
"""

from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from utils.pdf_processor import process_pdf
from utils.word_processor import process_word, is_word_file

app = FastAPI(title="File → Markdown Converter")


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


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    chunkable: bool = True,
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
    
    file_type = get_file_type(file.filename)
    
    if file_type == "pdf":
        return await process_pdf(file, chunkable)
    elif file_type == "word":
        return await process_word(file)
    else:
        supported_types = ['.pdf', '.doc', '.docx']
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Supported types: {', '.join(supported_types)}"
        )


@app.get("/")
async def root():
    """Health check and service info."""
    return {
        "service": "File to Markdown Converter",
        "supported_formats": [".pdf", ".doc", ".docx"],
        "endpoints": {
            "/extract": "POST - Upload file for conversion",
            "/": "GET - This info page"
        }
    }