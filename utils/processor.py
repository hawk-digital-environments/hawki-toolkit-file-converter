import io
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import yaml
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from kreuzberg import (
    ExtractionConfig,
    ExtractionResult,
    HierarchyConfig,
    ImageExtractionConfig,
    KeywordAlgorithm,
    KeywordConfig,
    LanguageDetectionConfig,
    OcrConfig,
    PageConfig,
    PdfConfig,
    extract_file,
)
from PIL import Image
from utils.helper import is_image, make_content_disposition
from typing import Any


@dataclass
class ElementNode:
    content: str
    starts_new_page: bool
    page_number: int | None


@dataclass
class Chunk:
    """The contents of a chunk."""

    content: str
    page_number: int | None


# https://docs.kreuzberg.dev/migration/from-unstructured/?h=unstructured#element-type-mapping
KREUZBERG_TEXT_ELEMENT_TYPES = frozenset(
    {
        "header",
        "narrative_text",
        "list_item",
        "table",
        "footer",
        "code_block",
        "block_quote",
    }
)


def get_extraction_config_for_file_content() -> ExtractionConfig:
    """The extraction config for a file.

    For kreuzberg configuration interface and defaults see:
        https://github.com/kreuzberg-dev/kreuzberg/blob/v4.9.5/packages/python/kreuzberg/_internal_bindings.pyi
    """
    return ExtractionConfig(
        include_document_structure=True,
        pdf_options=PdfConfig(
            extract_images=True,
            extract_metadata=True,
            hierarchy=HierarchyConfig(
                enabled=False,
            ),
        ),
        result_format="element_based",
        ocr=OcrConfig(
            backend="paddleocr",
        ),
        pages=PageConfig(
            extract_pages=True,
        ),
        images=ImageExtractionConfig(
            extract_images=True,
            auto_adjust_dpi=True,
        ),
        language_detection=LanguageDetectionConfig(detect_multiple=True),
    )


def build_chunk_header(
    file_name: str,
    keywords: list[str],
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
    if next_chunk:
        header_data["nextChunk"] = f"{(chunk + 1):05d}.md"
    if page_number:
        header_data["pageNumber"] = page_number

    yaml_block = yaml.safe_dump(
        header_data, sort_keys=False, allow_unicode=True
    ).strip()

    return f"---\n{yaml_block}\n---\n\n"


async def _resolve_image_element(
    element: dict,
    result: ExtractionResult,
    assets_dir: Path,
    image_counter: Generator[int, None, None],
) -> tuple[str, bool]:
    image_index = next(image_counter)
    image_data = result.images[image_index]["data"]

    img = Image.open(io.BytesIO(image_data))
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / f"image_{image_index}.png"
        img.save(tmp_file, format="PNG")
        saved_image_path, ocr = await process_image_content(tmp_file, assets_dir)

    return (
        f"\n> [Image: ../assets/{saved_image_path.name}]\n"
        + (f"> {ocr}\n" if ocr else ""),
        False,
    )


async def resolve_element_content(
    element: dict,
    result: ExtractionResult,
    assets_dir: Path,
    image_counter: Generator[int, None, None],
) -> tuple[str, bool]:
    """Map element types to chunk content."""
    etype = element["element_type"]

    if etype == "title":
        return element["text"], True
    if etype in KREUZBERG_TEXT_ELEMENT_TYPES:
        return element["text"], False
    if etype == "image":
        return await _resolve_image_element(element, result, assets_dir, image_counter)
    if etype == "page_break":
        return "", True
    return element["text"], False


async def make_element_nodes(
    elements: list[dict],
    result: ExtractionResult,
    assets_dir: Path,
) -> AsyncGenerator[ElementNode, None]:
    """Creates a processable/internal "ElementNode" from e.g. kreuzberg results."""
    image_counter = count(0)
    for element in elements:
        content, starts_new_page = await resolve_element_content(
            element, result, assets_dir, image_counter
        )
        yield ElementNode(
            content=content,
            starts_new_page=starts_new_page,
            page_number=element.get("metadata", {}).get("page_number"),
        )


async def accumulate_chunks(
    nodes: AsyncGenerator[ElementNode, None],
    max_chunk_length: int,
    has_pages: bool,
) -> AsyncGenerator[Chunk, None]:
    """"""
    chunk_buffer: list[str] = []
    buffer_length = 0
    current_page: int | None = None

    async for node in nodes:
        if has_pages and node.page_number is not None:
            if current_page is not None and node.page_number != current_page:
                if chunk_buffer:
                    yield Chunk("".join(chunk_buffer), current_page)
                    chunk_buffer = []
                    buffer_length = 0
            current_page = node.page_number

        would_overflow = buffer_length + len(node.content) > max_chunk_length

        if node.starts_new_page or (would_overflow and chunk_buffer):
            if chunk_buffer:
                yield Chunk("".join(chunk_buffer), current_page)
                chunk_buffer = []
                buffer_length = 0

        if len(node.content) > max_chunk_length:
            # TODO: add "smarter" chunking. E.g. not to write two words on a new page mid sentence -?
            for sub in chunked_content_iter(node.content, max_chunk_length):
                yield Chunk(sub, current_page)
            continue

        chunk_buffer.append(node.content)
        buffer_length += len(node.content)

    if chunk_buffer:
        yield Chunk("".join(chunk_buffer), current_page)


def chunked_content_iter(s: str, max_length: int = 100) -> Generator[str, None, None]:
    """
    Split text into chunks that:
    - prefer sentence boundaries
    - never exceed max_length
    - do NOT split decimal numbers like 3.14
    - fall back to word boundaries if a sentence is too long
    - finally hard-split very long words if needed
    """

    s = s.strip()
    if not s:
        return

    # Split after sentence-ending punctuation unless it's part of a decimal number
    # Examples:
    # "Hello.World" -> split
    # "12.345" -> do not split
    sentences = [
        part.strip()
        for part in re.split(
            # split on:
            # - ! or ?
            # - . when it's NOT between digits (so 12.345 stays intact)
            r"(?<=[!?])|(?<=\.)(?<!\d\.)|(?<=\.)(?!\d)",
            s,
        )
        if part.strip()
    ]

    # Decimal matcher (kept for oversized-token protection later)
    decimal_re = re.compile(r"^\d+\.\d+$")

    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()

        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            yield current
            current = ""

        # If sentence fits, keep it whole
        if len(sentence) <= max_length:
            current = sentence
            continue

        # Too long -> split by words
        words = sentence.split()
        word_chunk = ""

        for word in words:
            candidate = f"{word_chunk} {word}".strip()

            if len(candidate) <= max_length:
                word_chunk = candidate
                continue

            if word_chunk:
                yield word_chunk

            # Do NOT split decimal numbers like 12.345
            if decimal_re.fullmatch(word):
                word_chunk = word
                continue

            # Hard split only for non-decimal oversized words
            if len(word) > max_length:
                for i in range(0, len(word), max_length):
                    yield word[i : i + max_length]
                word_chunk = ""
            else:
                word_chunk = word

        if word_chunk:
            current = word_chunk

    if current:
        yield current


def write_chunk(
    tmp_chunk_file: Path, output_chunk_file: Path, chunk_header: str
) -> None:
    """Write a chunk from a temporary place to output directory."""
    with output_chunk_file.open("ab") as chunk_target:
        chunk_target.write(chunk_header.encode("utf-8"))
        with tmp_chunk_file.open("rb") as tmp_file:
            shutil.copyfileobj(tmp_file, chunk_target)


async def extract_keywords(chunk_file: Path, languages: list[str]) -> list[str]:
    chunk_keywords: list[str] = []
    for lang in languages:
        keyword_result = await extract_file(
            chunk_file,
            config=ExtractionConfig(
                keywords=KeywordConfig(
                    algorithm=KeywordAlgorithm.Yake,
                    language=lang,
                    max_keywords=10,
                    ngram_range=(1, 4),
                )
            ),
        )
        if keyword_result.extracted_keywords:
            keywords = sorted(
                [keyword.text for keyword in keyword_result.extracted_keywords]
            )
            chunk_keywords.extend(keywords)
    return chunk_keywords


async def finalize_chunk(
    chunk: Chunk,
    chunk_num: int,
    chunk_dir: Path,
    tmp_dir: str,
    languages: list[str],
    has_more: bool,
) -> list[str]:
    """Finalize a chunk by adding keywords and a header to a chunk file."""

    chunk_file_name = f"{chunk_num:05d}.md"
    tmp_chunk_path = Path(tmp_dir) / chunk_file_name

    with tmp_chunk_path.open("wb") as f:
        f.write(chunk.content.encode("utf-8"))

    keywords = await extract_keywords(tmp_chunk_path, languages)

    header = build_chunk_header(
        file_name=chunk_file_name,
        keywords=keywords,
        chunk=chunk_num,
        page_number=chunk.page_number,
        next_chunk=chunk_num + 1 if has_more else None,
    )

    output_path = chunk_dir / chunk_file_name
    write_chunk(tmp_chunk_path, output_path, header)

    return keywords


def _write_metadata(
    file_path: Path,
    result: ExtractionResult,
    total_chunks: int,
    languages: list[str],
    keywords: list[str],
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
    if val := getattr(result, "metadata", {}).get("created_at"):
        extraction_metadata["createdAt"] = val
    if keywords:
        extraction_metadata["keywords"] = keywords

    metadata_path = zip_dir / "meta.json"
    metadata_path.write_text(json.dumps(extraction_metadata, indent=2))


async def _annotate_last_async(aiterable: AsyncGenerator[Any, Any, Any]):
    """Wraps a generator to check if it has more items in it."""
    it = aiter(aiterable)
    prev = await anext(it, None)
    if prev is None:
        return
    async for item in it:
        yield prev, False
        prev = item
    yield prev, True


async def process_file_contents(
    file_path: Path, zip_dir: Path, assets_dir: Path
) -> None:
    """Extract the contents of a file into chunked markdown with metadata.

    For conceptual requirements and guide see:
        https://github.com/hawk-digital-environments/hawk-ixdlab-docs/blob/main/hawki/RAG/file_extractor/readme.md

    Pipeline:
        1. Extract file via kreuzberg (element-based result format)
        2. Stream elements into typed ElementNodes (async generator)
        3. Accumulate nodes into Chunks respecting character limits (async generator)
        4. Finalize each chunk (keywords + header + write)
        5. Write aggregate metadata
    """
    config = get_extraction_config_for_file_content()
    result = await extract_file(str(file_path), config=config)

    languages = result.detected_languages or [os.getenv("DEFAULT_LANGUAGE", "de")]
    max_chunk_length = int(os.getenv("MAX_CHUNK_LENGTH", 3000))
    has_pages = result.pages is not None

    chunk_dir = zip_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    nodes = make_element_nodes(result.elements, result, assets_dir)
    chunks = accumulate_chunks(nodes, max_chunk_length, has_pages)

    all_keywords: list[str] = []
    total_chunks = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        async for chunk, is_last in _annotate_last_async(chunks):
            total_chunks += 1
            keywords = await finalize_chunk(
                chunk,
                total_chunks,
                chunk_dir,
                tmp_dir,
                languages,
                has_more=not is_last,
            )
            all_keywords.extend(keywords)

    _write_metadata(file_path, result, total_chunks, languages, all_keywords, zip_dir)


async def process_file(
    file: UploadFile,
) -> StreamingResponse:
    """Process any supported file and return ZIP with markdown and images.

    Args:
        file: The uploaded file.
    """
    with TemporaryDirectory() as tmp_base:
        tmpdir = Path(tmp_base)

        zip_dir = tmpdir / "output"
        assets_dir = zip_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        filename = file.filename or "document"
        file_path = tmpdir / filename
        file_path.write_bytes(await file.read())

        if is_image(file):
            await process_image_content(file_path, assets_dir)
        else:
            await process_file_contents(file_path, zip_dir, assets_dir)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in zip_dir.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(zip_dir.parent))
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": make_content_disposition(Path(filename).stem)
            },
        )


def save_as_webp(
    image_file: Path,
    image_output_file: Path,
    max_size: tuple[int, int] = (2000, 2000),
    quality: int = 90,
):
    """Save image as webp file.

    Args:
        image_path: The path to the input image to convert.
        image_output_path: The path to the output image.
        max_size: Optional size adjustment.
    """
    with Image.open(image_file) as img:
        if img.mode not in ("RGB", "RGBA"):
            if "A" in img.getbands():
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        img.save(image_output_file, format="WEBP", quality=quality)
    return image_output_file


async def process_image_content(
    tmp_imagefile_path: Path, assets_dir: Path, language: str = "de"
):
    """Run ocr on an image file.

    Args:
        tmp_imagefile_path: The temporary image file.
        assets_dir: The output folder for assets like e.g. an image.
        language: The language to use.
    """
    config = ExtractionConfig(
        force_ocr=True,
        ocr=OcrConfig(
            backend="paddleocr",
            language=language,
        ),
    )
    result = await extract_file(str(tmp_imagefile_path), config=config)
    saved_image_path = save_as_webp(
        tmp_imagefile_path, assets_dir / tmp_imagefile_path.with_suffix(".webp").name
    )
    if result.ocr_elements:
        ocr_string = " || ".join(
            [
                elem["text"].strip()
                for elem in result.ocr_elements
                if elem["text"].strip()
            ]
        )
    else:
        ocr_string = ""
    if result.content:
        (assets_dir / Path(f"{tmp_imagefile_path.stem}_ocr.md")).write_text(
            result.content
        )
    return saved_image_path, ocr_string
