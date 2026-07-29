import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import ftfy
import yaml
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image
from xberg import (
    Chunk,
    ChunkingConfig,
    ExtractedDocument,
    ExtractInput,
    ExtractionConfig,
    ExtractionResult,
    HierarchyConfig,
    ImageExtractionConfig,
    Keyword,
    KeywordAlgorithm,
    KeywordConfig,
    LanguageDetectionConfig,
    OcrConfig,
    OcrElementConfig,
    PageConfig,
    PdfConfig,
    ResultFormat,
    extract,
)

from utils.helper import (
    is_image_filename,
    make_content_disposition,
)
from utils.language_helper import KeywordLanguageCodes, OcrLanguageCodes


def is_ocr_enabled() -> bool:
    """Whether OCR should run anywhere. Defaults to off; set OCR_ENABLED=true to enable."""
    return os.getenv("OCR_ENABLED", "true").strip().lower() in ("true", "1", "yes")


def is_save_document_image_refs_enabled() -> bool:
    """Whether document-extracted figures are saved and referenced in chunks.

    When true, each extracted figure is written as
    ``assets/image_{N}.webp`` and a ``> [Image: ...]`` reference is injected
    into the chunk markdown. When false, no webps are written and no references
    are injected -- but OCR text (from ``force_ocr``) is still present in the
    chunks. Defaults to on.
    """
    return os.getenv("SAVE_DOCUMENT_IMAGE_REFS", "false").strip().lower() in ("true", "1", "yes")


def get_extraction_config_for_file_content() -> ExtractionConfig:
    """The extraction config for a file.

    OCR and chunking are delegated to xberg in a single ``extract`` pass:
    ``force_ocr`` makes xberg OCR every page (and insert the recognized text
    into the content that gets chunked), and ``ChunkingConfig`` produces
    ``result.chunks`` directly. OCR is only configured when OCR_ENABLED is on,
    so the no-OCR path simply extracts the embedded text layer.

    For xberg configuration interface and defaults see:
        https://docs.xberg.io/reference/configuration/
    """
    config: ExtractionConfig = {
        "include_document_structure": True,
        "pdf_options": PdfConfig(
            extract_images=True,
            extract_metadata=True,
            hierarchy=HierarchyConfig(
                enabled=False,
            ),
        ),
        "result_format": ResultFormat.ELEMENT_BASED,
        "pages": PageConfig(
            extract_pages=True,
        ),
        "images": ImageExtractionConfig(
            extract_images=True,
            inject_placeholders=True,
            output_format="webp",
            auto_adjust_dpi=True,
            max_image_dimension=1280,
        ),
        "chunking": ChunkingConfig(
            chunker_type="text",
            max_characters=int(os.getenv("MAX_CHUNK_LENGTH", "3000")),
            overlap=int(os.getenv("CHUNK_OVERLAP", "0")),
            trim=True,
        ),
    }
    if is_ocr_enabled():
        ocr = OcrLanguageCodes.from_env()
        # force_ocr is intentionally NOT set: xberg auto-OCRs scanned pages and
        # always OCRs embedded figures via run_ocr_on_images (default True).
        # Forcing OCR here re-OCRs pages that already have a text layer while
        # run_ocr_on_images also OCRs their figures, duplicating the text.
        config["ocr"] = OcrConfig(
            backend=ocr.backend,
            language=ocr.languages,
            element_config=OcrElementConfig(include_elements=True),
        )
    return config


def get_extraction_config_for_image() -> ExtractionConfig:
    """The extraction config for a standalone uploaded image.

    A single ``extract`` pass does everything: xberg re-encodes the image to
    webp (``output_format='webp'``) so ``result.images[0].data`` is ready to
    write, and -- when OCR is enabled -- ``force_ocr`` produces the recognized
    text in ``result.content``. ``run_ocr_on_images=False`` avoids the image
    being OCR'd twice (force_ocr already covers it). No chunking: an image
    yields one OCR document, not chunks.
    """
    config: ExtractionConfig = {
        "images": ImageExtractionConfig(
            extract_images=True,
            run_ocr_on_images=False,
            output_format="webp",
            auto_adjust_dpi=True,
            max_image_dimension=1280,
        ),
    }
    if is_ocr_enabled():
        ocr = OcrLanguageCodes.from_env()
        config["force_ocr"] = True
        config["ocr"] = OcrConfig(
            backend=ocr.backend,
            language=ocr.languages,
            element_config=OcrElementConfig(include_elements=True),
        )
    return config


def _unwrap_single(result: ExtractionResult) -> ExtractedDocument:
    """Return the single document from an extraction result envelope.

    xberg's ``extract`` returns an ``ExtractionResult`` envelope with a
    ``results`` list and an ``errors`` list. For single-file extraction we
    expect exactly one document; surface any error otherwise.
    """
    if result.errors:
        err = result.errors[0]
        raise RuntimeError(getattr(err, "message", None) or str(err))
    if not result.results:
        raise RuntimeError("Extraction produced no results.")
    return result.results[0]


def build_chunk_header(
    file_name: str,
    keywords: list[str],
    languages: list[str],
    chunk: int,
    page_number: None | int,
    next_chunk: int | None,
) -> str:
    header_data = {
        "file": file_name,
        "chunk": chunk,
    }

    if keywords:
        header_data["keywords"] = keywords
    if languages:
        header_data["languages"] = languages
    if next_chunk:
        header_data["nextChunk"] = f"{(chunk + 1):05d}.md"
    if page_number:
        header_data["pageNumber"] = page_number

    yaml_block = yaml.safe_dump(header_data, sort_keys=False, allow_unicode=True).strip()

    return f"---\n{yaml_block}\n---\n\n"


def _save_extracted_images(result: ExtractedDocument, assets_dir: Path) -> None:
    """Save each extracted figure as ``image_{N}.webp`` under ``assets_dir``.

    xberg re-encodes the figures to webp during extraction
    (``ImageExtractionConfig.output_format='webp'``), so ``image.data`` is
    ready-to-write webp bytes -- no PIL conversion needed. OCR of the document
    is also handled by xberg, so each figure's text already lives in the
    chunks; this only persists the image binaries.
    """
    for index, image in enumerate(result.images or []):
        (assets_dir / f"image_{index}.webp").write_bytes(image.data)


def _render_chunk_content(chunk: Chunk, inject_refs: bool) -> str:
    """Build the markdown body for a chunk: optional image references + text.

    When ``inject_refs`` is true, each figure the chunk covers (per
    ``metadata.image_indices``) is surfaced as a ``> [Image: ...]`` reference
    pointing at the saved webp asset. When false, no reference is injected --
    but the chunk text (including any OCR'd content from ``force_ocr``) is
    still returned unchanged.
    """
    if not inject_refs:
        return chunk.content
    refs = "".join(
        f"\n> [Image: ../assets/image_{idx}.webp]\n" for idx in (chunk.metadata.image_indices or [])
    )
    return f"{refs}{chunk.content}"


def write_chunk(tmp_chunk_file: Path, output_chunk_file: Path, chunk_header: str) -> None:
    """Write a chunk from a temporary place to output directory."""
    with output_chunk_file.open("ab") as chunk_target:
        chunk_target.write(chunk_header.encode("utf-8"))
        with tmp_chunk_file.open("rb") as tmp_file:
            shutil.copyfileobj(tmp_file, chunk_target)


async def detect_chunk_language(chunk_file: Path) -> list[str]:
    """Detect the language(s) of a chunk's content via xberg language detection.

    Runs a dedicated ``extract`` pass with ``LanguageDetectionConfig`` on the
    temp ``.md`` file (the same file keyword extraction runs on). Returns the
    detected language codes normalized to ISO 639-1 (e.g. ``["en"]``) for
    surfacing in the chunk header and ``meta.json``; the caller maps them to a
    KeywordConfig-supported code (or ``None``). ``mime_type`` is set to
    suppress content-sniffing (see :func:`extract_keywords`).

    ``min_confidence`` defaults to 0.5 (env: ``LANGUAGE_DETECTION_MIN_CONFIDENCE``)
    rather than kreuzberg's 0.8 default because OCR'd chunk text is short and
    noisy -- the default threshold detects nothing on typical chunks.
    """
    result = await extract(
        ExtractInput(kind="uri", uri=str(chunk_file), mime_type="text/markdown"),
        config=ExtractionConfig(
            language_detection=LanguageDetectionConfig(
                enabled=True,
                min_confidence=float(os.getenv("LANGUAGE_DETECTION_MIN_CONFIDENCE", "0.5")),
                detect_multiple=False,
            ),
        ),
    )
    document = _unwrap_single(result)
    return [KeywordLanguageCodes.to_iso639_1(lang) for lang in (document.detected_languages or [])]


async def extract_keywords(chunk_file: Path, language: str | None) -> list[Keyword]:
    """Extract keywords from the markdown chunk files.

    Returns the xberg :class:`Keyword` objects (carrying ``.text`` and
    ``.score``) so the caller can rank by score for ``meta.json``. Deduplicated
    by text (first occurrence kept).
    """
    keyword_result = await extract(
        ExtractInput(kind="uri", uri=str(chunk_file), mime_type="text/markdown"),
        config=ExtractionConfig(
            keywords=KeywordConfig(
                algorithm=KeywordAlgorithm.YAKE,
                max_keywords=int(os.getenv("MAX_KEYWORDS_FOR_LANGUAGE", "10")),
                language=language,
            )
        ),
    )
    document = _unwrap_single(keyword_result)
    if not document.extracted_keywords:
        return []
    # Dedupe by text, keeping the first Keyword (preserves its score).
    seen: dict[str, Keyword] = {}
    for kw in document.extracted_keywords:
        if kw.text not in seen:
            seen[kw.text] = kw
    return list(seen.values())


def _sanitize_text_content(text: str) -> str:
    """These code points are valid Unicode and therefore survive UTF-8 encoding,
    but MIME sniffers such as libmagic may interpret their presence as evidence
    of binary data and classify the file as application/octet-stream instead of text/plain.
    Only control characters are removed;
    whitespace (\\t, \\n, \\r) and all printable text (umlauts, dashes, emoji, ...) are preserved.
    """

    _CONTROL_CHARS_RE = re.compile(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f"
        r"\u200b"  # zero-width space/joiner characters
        r"\u200e\u200f"  # bidi marks
        r"\u2028\u2029"  # line/paragraph separators
        r"\u202a-\u202e"  # bidi overrides
        r"\u2066-\u2069"  # bidi isolates
        r"\ufeff]"  # BOM
    )
    return ftfy.fix_text(_CONTROL_CHARS_RE.sub("", text))


async def finalize_chunk(
    content: str,
    page_number: int | None,
    chunk_num: int,
    chunk_dir: Path,
    tmp_dir: str,
    has_more: bool,
) -> tuple[list[Keyword], list[str]]:
    """Finalize a chunk by detecting its language, extracting keywords, and
    writing a header to a chunk file.

    Language detection runs before keyword extraction so the detected code can
    drive KeywordConfig's stopword filtering (mapped to a supported code or
    ``None``). Returns ``(keywords, detected_languages)`` -- keywords as the
    xberg :class:`Keyword` objects (for score-based ranking) -- so the caller
    can aggregate both across chunks into ``meta.json``.
    """

    chunk_file_name = f"{chunk_num:05d}.md"
    tmp_chunk_path = Path(tmp_dir) / chunk_file_name

    sanitized = _sanitize_text_content(content)
    with tmp_chunk_path.open("wb") as f:
        f.write(sanitized.encode("utf-8"))

    detected_languages = await detect_chunk_language(tmp_chunk_path)
    keyword_language = KeywordLanguageCodes.language(detected_languages)
    keywords = await extract_keywords(tmp_chunk_path, keyword_language)

    header = build_chunk_header(
        file_name=chunk_file_name,
        keywords=sorted((kw.text for kw in keywords), key=str.casefold),
        languages=detected_languages,
        chunk=chunk_num,
        page_number=page_number,
        next_chunk=chunk_num + 1 if has_more else None,
    )

    output_path = chunk_dir / chunk_file_name
    write_chunk(tmp_chunk_path, output_path, header)

    return keywords, detected_languages


def _write_metadata(
    file_path: Path,
    result: ExtractedDocument,
    total_chunks: int,
    languages: list[str],
    keywords: list[Keyword],
    zip_dir: Path,
) -> None:
    extraction_metadata: dict = {
        "name": file_path.name,
        "size": file_path.stat().st_size,
        "chunks": total_chunks,
        "mimeType": result.mime_type,
    }
    if languages:
        extraction_metadata["languages"] = languages
    if result.metadata and (val := result.metadata.created_at):
        extraction_metadata["createdAt"] = val
    if keywords:
        # Keep the 50 best-scoring keywords for meta.json
        ranked_kw = sorted(
            keywords,
            key=lambda kw: (-kw.score),
        )[:50]
        extraction_metadata["keywords"] = [kw.text for kw in ranked_kw]

    metadata_path = zip_dir / "meta.json"
    metadata_path.write_text(json.dumps(extraction_metadata, indent=2), encoding="utf-8")


async def process_file_contents(file_path: Path, zip_dir: Path, assets_dir: Path) -> None:
    """Extract a file into chunked markdown plus aggregate metadata.

    OCR and chunking are both performed by xberg in a single ``extract`` pass
    (see ``get_extraction_config_for_file_content``). This writes one
    ``chunks/NNNNN.md`` per ``result.chunks`` entry (each with per-chunk YAKE
    keywords and a YAML header), the extracted figures as ``assets/*.webp``,
    and a top-level ``meta.json``.

    For conceptual requirements and guide see:
        https://github.com/hawk-digital-environments/hawk-ixdlab-docs/blob/main/hawki/RAG/file_extractor/readme.md
    """
    config = get_extraction_config_for_file_content()
    result = _unwrap_single(
        await extract(ExtractInput(kind="uri", uri=str(file_path)), config=config)
    )

    save_image_refs = is_save_document_image_refs_enabled()
    if save_image_refs:
        _save_extracted_images(result, assets_dir)

    chunk_dir = zip_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    chunks = result.chunks or []
    total_chunks = len(chunks)
    all_keywords: list[Keyword] = []
    all_languages: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, chunk in enumerate(chunks):
            keywords, languages = await finalize_chunk(
                content=_render_chunk_content(chunk, save_image_refs),
                page_number=chunk.metadata.first_page,
                chunk_num=i + 1,
                chunk_dir=chunk_dir,
                tmp_dir=tmp_dir,
                has_more=i < total_chunks - 1,
            )
            all_keywords.extend(keywords)
            all_languages.extend(languages)

    # Deduplicate per-chunk detected languages (stable sort) for meta.json.
    unique_languages = sorted(set(all_languages), key=str.casefold)
    _write_metadata(file_path, result, total_chunks, unique_languages, all_keywords, zip_dir)


async def process_file_core(
    file_bytes: bytes,
    filename: str,
) -> tuple[bytes, dict[str, str]]:
    """Core file processing. Returns (zip_bytes, response_headers).

    Args:
        file_bytes: Raw file content.
        filename: Sanitized filename.
    """
    with TemporaryDirectory() as tmp_base:
        tmpdir = Path(tmp_base)

        zip_dir = tmpdir / "output"
        assets_dir = zip_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        file_path = tmpdir / filename
        file_path.write_bytes(file_bytes)

        if is_image_filename(filename):
            await process_image_content(file_path, assets_dir)
        else:
            await process_file_contents(file_path, zip_dir, assets_dir)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in zip_dir.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(zip_dir.parent))
        buf.seek(0)

        headers = {"Content-Disposition": make_content_disposition(Path(filename).stem)}

        return buf.getvalue(), headers


async def process_file(
    file: UploadFile,
) -> StreamingResponse:
    """Process any supported file and return ZIP with markdown and images."""
    file_bytes = await file.read()
    zip_bytes, headers = await process_file_core(file_bytes, file.filename or "document")
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers=headers,
    )


async def process_image_content(tmp_imagefile_path: Path, assets_dir: Path):
    """Save an uploaded image as a webp asset and run OCR on it.

    A single xberg ``extract`` pass does both jobs: it re-encodes the image to
    webp (``output_format='webp'`` -> ``result.images[0].data``) and, when OCR
    is enabled, force-OCRs it into ``result.content``. PIL is used only to read
    the source MIME type -- the conversion is entirely xberg's.

    Args:
        tmp_imagefile_path: The image file on disk (e.g. an uploaded image).
        assets_dir: The output folder for assets (webp image + OCR markdown).
    """
    data = tmp_imagefile_path.read_bytes()
    mime = Image.open(io.BytesIO(data)).get_format_mimetype()

    config = get_extraction_config_for_image()
    result = _unwrap_single(
        await extract(ExtractInput(kind="bytes", bytes=data, mime_type=mime), config=config)
    )

    saved_image_path = assets_dir / tmp_imagefile_path.with_suffix(".webp").name
    images = result.images or []
    if images:
        saved_image_path.write_bytes(images[0].data)

    ocr_string = ""
    if result.ocr_elements:
        ocr_string = " ".join(
            elem.text.strip() for elem in result.ocr_elements if elem.text.strip()
        )
    if result.content:
        (assets_dir / f"{tmp_imagefile_path.stem}_ocr.md").write_text(
            result.content, encoding="utf-8"
        )
    return saved_image_path, ocr_string
