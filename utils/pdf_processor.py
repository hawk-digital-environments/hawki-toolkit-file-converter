#!/usr/bin/env python3
"""
PDF-to-Markdown processor with OCR fallback.

Features
--------
• Size-aware chunking
• Parallel page extraction (with ThreadPool)
• OCR fallback for scanned PDFs
• Image export
• ZIP output
"""

import asyncio
import io
import re
import zipfile
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from langdetect import detect  # for auto language detection

from utils.helper import make_content_disposition

# ──────────────────────────── Tunables ──────────────────────────── #
MB = 1_048_576  # 1024²
CHUNK_THRESHOLD = 50 * MB
CHUNK_TARGET = 20 * MB
MIN_PAGES = 50
FIRST_PASS_STEP = 20
DEBUG = False
OCR_LANGS = "eng+deu+fra+ita+spa+por+nld"  # Add European languages
# ────────────────────────────────────────────────────────────────── #


# ────────────────────── Utility Helpers ─────────────────────────── #
def _log(msg: str) -> None:
    if DEBUG:
        print(msg)


def clean_text(txt: str) -> str:
    """Normalize Unicode and collapse extra whitespace."""
    txt = unicodedata.normalize("NFKC", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return txt.strip()


def slice_ranges(total_pages: int, step: int) -> List[Tuple[int, int]]:
    """Yield (start, end) page ranges with fixed step size."""
    return [(i, min(i + step, total_pages)) for i in range(0, total_pages, step)]


def detect_language(text: str) -> str:
    """Detect language of given text, fallback to English."""
    try:
        lang = detect(text)
        return lang
    except Exception:
        return "eng"  # default


# ────────────────── Chunk Splitter by Size ───────────────── #
def split_by_size(
    doc: fitz.Document,
    start: int,
    end: int,
    *,
    chunkable: bool,
    bucket: List[Tuple[int, int]],
) -> None:
    """Append (start, end) to *bucket* based on size thresholds."""
    if not chunkable or (end - start) <= MIN_PAGES:
        bucket.append((start, end))
        return

    subdoc = fitz.open()
    subdoc.insert_pdf(doc, from_page=start, to_page=end - 1)
    size = len(subdoc.write())
    subdoc.close()

    if size <= CHUNK_TARGET or size <= CHUNK_THRESHOLD:
        bucket.append((start, end))
    else:
        step = max((end - start) // 4, 1)
        for i in range(start, end, step):
            split_by_size(doc, i, min(i + step, end), chunkable=chunkable, bucket=bucket)


# ──────────────── Page/Chunk Processor with OCR ─────────────── #
def extract_chunk(
    chunk_id: int,
    doc: fitz.Document,
    start: int,
    end: int,
    img_dir: Path,
) -> str:
    """Extract markdown content from PDF pages with OCR fallback."""
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=start, to_page=end - 1)
    parts: List[str] = [f"# Chunk {start + 1}-{end}"]

    for page_number, page in enumerate(sub, start=start + 1):
        text = page.get_text("blocks")
        text = "\n".join(b[4].strip() for b in text if b[4].strip())
        used_ocr = False

        if not text.strip():
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            # OCR fallback
            text = pytesseract.image_to_string(img, lang=OCR_LANGS)
            text = clean_text(text)
            used_ocr = True

        images_here = []
        for img_idx, img_info in enumerate(page.get_images(full=True), start=1):
            xref = img_info[0]
            info = sub.extract_image(xref)
            ext = info["ext"]
            img_path = img_dir / f"c{chunk_id}_p{page_number}_i{img_idx}.{ext}"
            img_path.write_bytes(info["image"])
            images_here.append(img_path.name)

        if text or images_here:
            header = f"## Page {page_number}"
            if used_ocr:
                header += " (OCR)"
            parts.append(header)

            if text:
                parts.append(text)
            for img_name in images_here:
                parts.append(f"![p{page_number}](/images_pdf/{img_name})")

    sub.close()
    return "\n\n".join(parts)


# ────────────────────── Main PDF Processor ─────────────────────── #
async def process_pdf(file: UploadFile, chunkable: bool = True) -> StreamingResponse:
    """Process PDF file and return ZIP with markdown and images."""
    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        pdf_path = tmpdir / file.filename
        pdf_path.write_bytes(await file.read())

        out_dir = tmpdir / "output"
        img_dir = out_dir / "images_pdf"
        img_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        total_pages = doc.page_count

        first_pass = slice_ranges(total_pages, FIRST_PASS_STEP)
        ranges: List[Tuple[int, int]] = []
        for s, e in first_pass:
            split_by_size(doc, s, e, chunkable=chunkable, bucket=ranges)

        _log(f"✂️  Final chunk count: {len(ranges)}")

        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None, extract_chunk, idx, doc, s, e, img_dir
            )
            for idx, (s, e) in enumerate(ranges)
        ]
        markdown_blocks = await asyncio.gather(*tasks)
        doc.close()

        md_path = out_dir / "content_markdown.md"
        md_path.write_text("\n\n".join(markdown_blocks), encoding="utf-8")

        # ZIP everything
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out_dir.rglob("*"):
                z.write(p, p.relative_to(out_dir.parent))
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": make_content_disposition(pdf_path.stem)},
        )
