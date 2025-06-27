#!/usr/bin/env python3
"""
FastAPI PDF-to-Markdown service.

Features
--------
• Optional size-aware chunking
• Parallel page extraction (with Threadpool)
• Image export
• Single-ZIP response 
"""

import asyncio
import io
import re
import zipfile
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Tuple

import fitz  
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse

# ──────────────────────────── Tunables ──────────────────────────── #
MB = 1_048_576  # 1024²
CHUNK_THRESHOLD = 50 * MB      # when to start splitting
CHUNK_TARGET     = 20 * MB      # desired max chunk size
MIN_PAGES        = 50            # don't split below this
FIRST_PASS_STEP  = 20           # initial pages per slice
DEBUG            = False        # for console logs
# ────────────────────────────────────────────────────────────────── #

app = FastAPI(title="PDF → MD Extractor")


# ────────────────────── Utility helpers ─────────────────────────── #
def _log(msg: str) -> None:
    if DEBUG:
        print(msg)


def clean_text(txt: str) -> str:
    """Normalise Unicode and collapse superfluous whitespace."""
    txt = unicodedata.normalize("NFKC", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    return txt.strip()


def slice_ranges(total_pages: int, step: int) -> List[Tuple[int, int]]:
    """Yield (start, end) page ranges with a fixed step size."""
    return [(i, min(i + step, total_pages)) for i in range(0, total_pages, step)]


# ─────────────────── Size-aware chunk splitter ──────────────────── #
def split_by_size(
    doc: fitz.Document,
    start: int,
    end: int,
    *,
    chunkable: bool,
    bucket: List[Tuple[int, int]],
) -> None:
    """
    Append (start, end) tuples to *bucket* so that each resulting
    sub-document is ≤ CHUNK_TARGET bytes **or** ≤ MIN_PAGES pages.
    """
    if not chunkable or (end - start) <= MIN_PAGES:
        bucket.append((start, end))
        return

    subdoc = fitz.open()         
    subdoc.insert_pdf(doc, from_page=start, to_page=end - 1)
    size = len(subdoc.write())
    subdoc.close()

    if size <= CHUNK_TARGET:
        bucket.append((start, end))
    elif size <= CHUNK_THRESHOLD:
        # not huge, to avoid oversplitting!!!! Important
        bucket.append((start, end))
    else:
        # split into 4 roughly equal parts
        step = max((end - start) // 4, 1)
        for i in range(start, end, step):
            split_by_size(doc, i, min(i + step, end), chunkable=chunkable, bucket=bucket)


# ────────────────── Page/Chunk processing routine ───────────────── #
def extract_chunk(
    chunk_id: int,
    doc: fitz.Document,
    start: int,
    end: int,
    img_dir: Path,
) -> str:
    """Run **synchronously** inside a thread pool → returns markdown."""
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=start, to_page=end - 1)
    parts: List[str] = [f"# Chunk {start + 1}-{end}"]

    for page_number, page in enumerate(sub, start=start + 1):
        text = page.get_text("blocks")
        text = "\n".join(b[4].strip() for b in text if b[4].strip())

        images_here = []
        for img_idx, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            info = sub.extract_image(xref)
            ext  = info["ext"]
            img_path = img_dir / f"c{chunk_id}_p{page_number}_i{img_idx}.{ext}"
            img_path.write_bytes(info["image"])
            images_here.append(img_path.name)

        if text or images_here:
            parts.append(f"## Page {page_number}")
            if text:
                parts.append(clean_text(text))
            for img in images_here:
                parts.append(f"![p{page_number}](/images_pdf/{img})")

    sub.close()
    return "\n\n".join(parts)


# ─────────────────────────── API route ──────────────────────────── #
@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    chunkable: bool = True,
):
    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        pdf_path = tmpdir / file.filename
        pdf_path.write_bytes(await file.read())        

        out_dir = tmpdir / "output"
        img_dir = out_dir / "images_pdf"
        img_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        total_pages = doc.page_count

        # Decide initial ranges
        first_pass = slice_ranges(total_pages, FIRST_PASS_STEP)
        ranges: List[Tuple[int, int]] = []
        for s, e in first_pass:
            split_by_size(doc, s, e, chunkable=chunkable, bucket=ranges)

        _log(f"✂️  Final chunk count: {len(ranges)}")

        # Parallel extraction
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None, extract_chunk, idx, doc, s, e, img_dir
            )
            for idx, (s, e) in enumerate(ranges)
        ]
        markdown_blocks = await asyncio.gather(*tasks)
        doc.close()

        # Write combined markdown
        md_path = out_dir / "content_markdown.md"
        md_path.write_text("\n\n".join(markdown_blocks), encoding="utf-8")

        # Zip everything
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out_dir.rglob("*"):
                z.write(p, p.relative_to(out_dir.parent))
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{pdf_path.stem}.zip"'},
        )
