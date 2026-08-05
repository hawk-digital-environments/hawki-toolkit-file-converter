"""Regression tests for :func:`utils.processor.finalize_chunk`.

Chunk content that begins with an image-magic byte sequence (e.g. ``"BM"`` --
the BMP signature, as produced by OCR of ``hpul.pdf``: ``"BMAS,
Bundesministerium ..."``) used to make xberg content-sniff the temp ``.md`` file
as ``image/bmp`` and hard-fail inside :func:`extract_keywords` with
``"Unknown bitmap header type"``. Passing ``mime_type="text/markdown"`` on the
:class:`ExtractInput` suppresses the sniff; these tests pin that behavior.
"""

from pathlib import Path

import pytest

from utils.processor import finalize_chunk


@pytest.mark.asyncio
async def test_finalize_chunk_content_starting_with_bmp_magic(tmp_path: Path) -> None:
    """A chunk whose body starts with the BMP magic ``"BM"`` must not crash
    keyword extraction.

    Without ``mime_type`` on the ``ExtractInput`` (utils/processor.py), xberg
    sniffs the temp ``.md`` file, sees ``"BM"`` at offset 0, routes it to the
    BMP decoder and raises ``RuntimeError: Parsing error: Failed to decode
    image: ... Unknown bitmap header type``. This is the hpul.pdf chunk-249
    failure.
    """
    chunk_dir = tmp_path / "chunks"
    tmp_dir = tmp_path / "tmp"
    chunk_dir.mkdir()
    tmp_dir.mkdir()

    # Real-world trigger: OCR'd text from hpul.pdf chunk 249 ("BMAS, ..."),
    # whose first two bytes are the BMP magic "BM".
    body = "BMAS, Bundesministerium fuer Arbeit und Soziales, 2018)."

    keywords, languages = await finalize_chunk(
        content=body,
        page_number=1,
        chunk_num=1,
        chunk_dir=chunk_dir,
        tmp_dir=str(tmp_dir),
        has_more=False,
    )

    # Keyword extraction completed instead of raising RuntimeError.
    assert isinstance(keywords, list)
    # finalize_chunk now also returns the chunk's detected languages.
    assert isinstance(languages, list)

    # The chunk file is written and carries the original body intact.
    chunk_file = chunk_dir / "00001.md"
    assert chunk_file.is_file()
    assert body in chunk_file.read_text(encoding="utf-8")
