import re
from pathlib import Path

import pytest


@pytest.fixture
def pdf_file(testdata_dir) -> Path:
    """Return the path to the same-origin PDF test file."""
    return testdata_dir / "same_origin_export_to_pdf_and_doc.pdf"


@pytest.fixture
def doc_file(testdata_dir) -> Path:
    """Return the path to the same-origin DOCX test file."""
    return testdata_dir / "same_origin_export_to_pdf_and_doc.docx"


@pytest.fixture
def chunk_env(monkeypatch, max_chunks):
    """Force one-character-per-chunk (mirrors test_chunking.py's chunk_env)."""
    monkeypatch.setenv("MAX_CHUNK_LENGTH", str(max_chunks))


@pytest.fixture
def pdf_chunk_content():
    def _pdf_chunk_content(pdf_entries: dict[str, bytes], chunk_num: int) -> str:
        """Return a PDF chunk's markdown body without its YAML header."""
        text = pdf_entries[f"output/chunks/{chunk_num:05d}.md"].decode("utf-8")
        match = re.search(r"---\n.*?\n---\n?(.*)", text, re.DOTALL)
        return match.group(1) if match else text

    return _pdf_chunk_content


@pytest.mark.parametrize("max_chunks", [1, 3])
@pytest.mark.usefixtures("chunk_env")
def test_pdf_and_doc_chunks_are_equal(
    client,
    auth_headers,
    pdf_file,
    doc_file,
    monkeypatch,
    extract_zip_entries,
    assert_zip_response,
    assert_markdown_content,
    pdf_chunk_content,
    max_chunks,
) -> None:
    """With MAX_CHUNK_LENGTH set via env the same-origin PDF and DOCX must produce
    equivalent chunked text.

    Historically the kreuzberg/xberg chunker handled PDFs and DOCs differently.
    This test uploads both exports of the same source document with chunking
    forced to one character per chunk and asserts that every DOC chunk's body
    equals the corresponding PDF chunk's body. Only the body is compared.
    Image-ref injection is disabled so the comparison covers pure chunk text.
    """
    # GIVEN test skips image extraction
    monkeypatch.setenv("SAVE_DOCUMENT_IMAGE_REFS", "false")

    # WHEN pdf file content is extracted
    with open(pdf_file, "rb") as f:
        pdf_response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )
    assert_zip_response(pdf_response, "bar.pdf.zip")
    pdf_entries = extract_zip_entries(pdf_response)

    # AND doc file content is extracted
    with open(doc_file, "rb") as f:
        doc_response = client.post(
            "/extract",
            files={"file": ("foo.docx", f, "application/msword")},
            headers=auth_headers,
        )
    assert_zip_response(doc_response, "foo.doc.zip")
    doc_entries = extract_zip_entries(doc_response)

    # AND chunks are extracted from both runs
    pdf_chunks = sorted(n for n in pdf_entries if n.startswith("output/chunks/"))
    doc_chunks = sorted(n for n in doc_entries if n.startswith("output/chunks/"))

    # THEN chunk count is equal
    assert len(pdf_chunks) == len(doc_chunks), (
        f"Expected 94 chunks each; got pdf={len(pdf_chunks)} doc={len(doc_chunks)}."
    )

    # AND Each DOC chunk body must equal the corresponding PDF chunk body.
    for i in range(1, len(pdf_chunks) + 1):
        assert_markdown_content(
            f"output/chunks/{i:05d}.md",
            pdf_chunk_content(pdf_entries, i),
            doc_entries,
        )
