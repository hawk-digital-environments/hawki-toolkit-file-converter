from pathlib import Path

import pytest


@pytest.fixture
def pdf_file(testdata_dir) -> Path:
    """Return the path to the sample PDF test file."""
    return testdata_dir / "same_origin_export_to_pdf_and_doc.pdf"


@pytest.fixture
def expected_pdf_md_content() -> str:
    """Return the expected markdown content from PDF extraction."""
    return (
        "\n\n> [Image: ../assets/image_0.webp]\n"
        + "Foobar"
        + "\n\n"
        + "HOLIDAY THEME OCR TEST\n\nENGLISH WORDS DEUTSCHE WÖRTER\nBEACH STRAND\nRELAX URLAUB\nSUMMER SONNE\n\nTRAVEL MEER"
    )


@pytest.fixture
def expected_pdf_md_header() -> dict:
    """Return the expected PDF header in markdown."""
    return {
        "chunk": 1,
        "file": "00001.md",
        "languages": ["en"],
        "keywords": [
            "beach strand relax",
            "deutsche wörter beach",
            "foobar holiday theme",
            "holiday theme ocr",
            "ocr test english",
            "relax urlaub summer",
            "sonne travel meer",
            "strand relax urlaub",
            "theme ocr test",
            "wörter beach strand",
        ],
        "pageNumber": 1,
    }


@pytest.fixture
def expected_pdf_metadata() -> dict:
    """Return the expected PDF metadata."""
    return {
        "name": "bar.pdf",
        "size": 1216058,
        "chunks": 1,
        "mimeType": "application/pdf",
        "languages": ["en"],
        "keywords": [
            "foobar holiday theme",
            "sonne travel meer",
            "holiday theme ocr",
            "theme ocr test",
            "ocr test english",
            "deutsche wörter beach",
            "wörter beach strand",
            "beach strand relax",
            "strand relax urlaub",
            "relax urlaub summer",
        ],
    }


def test_extract_pdf_returns_zip(
    client,
    auth_headers,
    pdf_file,
    expected_pdf_md_content,
    extract_zip_entries,
    assert_zip_response,
    expected_pdf_metadata,
    assert_metadata_content,
    assert_markdown,
    expected_pdf_md_header,
) -> None:
    """Test that posting a PDF returns a valid zip with markdown and images."""
    with open(pdf_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        [
            "output/assets/image_0.webp",
            "output/chunks/00001.md",
            "output/meta.json",
        ]
    )
    assert_markdown(
        "output/chunks/00001.md",
        expected_pdf_md_content,
        expected_pdf_md_header,
        entries,
    )
    assert_metadata_content("output/meta.json", expected_pdf_metadata, entries)


@pytest.fixture
def expected_pdf_md_content_no_ocr() -> str:
    """Return the expected markdown content from PDF extraction with OCR off."""
    return "\n\n> [Image: ../assets/image_0.webp]\nFoobar"


@pytest.fixture
def expected_pdf_md_header_no_ocr() -> dict:
    """Return the expected PDF header in markdown with OCR off.

    No keywords: YAKE finds nothing useful in the minimal no-OCR content.
    No languages: the single token "Foobar" is below the language-detection
    confidence threshold, so no language is detected for this chunk.
    """
    return {"chunk": 1, "file": "00001.md", "pageNumber": 1}


@pytest.fixture
def expected_pdf_metadata_no_ocr() -> dict:
    """Return the expected PDF metadata with OCR off.

    No keywords key (YAKE empty). No languages key: "Foobar" alone is below
    the language-detection confidence threshold.
    """
    return {
        "name": "bar.pdf",
        "size": 1216058,
        "chunks": 1,
        "mimeType": "application/pdf",
    }


def test_extract_pdf_returns_zip_no_ocr(
    client,
    auth_headers,
    pdf_file,
    monkeypatch,
    expected_pdf_md_content_no_ocr,
    expected_pdf_md_header_no_ocr,
    expected_pdf_metadata_no_ocr,
    extract_zip_entries,
    assert_zip_response,
    assert_markdown,
    assert_metadata_content,
) -> None:
    """OCR disabled: image still extracted as webp, but no OCR caption and no _ocr.md.

    Mirrors test_extract_pdf_returns_zip but with OCR_ENABLED=false, showing the
    difference: the per-image OCR caption and the image_0_ocr.md asset disappear,
    while the image itself is still saved and the page text is still extracted.
    """
    monkeypatch.setenv("OCR_ENABLED", "false")

    with open(pdf_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    # Key difference from test_extract_pdf_returns_zip: no image_0_ocr.md.
    assert sorted([name for name in entries]) == sorted(
        [
            "output/assets/image_0.webp",
            "output/chunks/00001.md",
            "output/meta.json",
        ]
    )
    assert_markdown(
        "output/chunks/00001.md",
        expected_pdf_md_content_no_ocr,
        expected_pdf_md_header_no_ocr,
        entries,
    )
    assert_metadata_content("output/meta.json", expected_pdf_metadata_no_ocr, entries)


@pytest.fixture
def expected_pdf_md_content_no_refs() -> str:
    """OCR-on content when SAVE_DOCUMENT_IMAGE_REFS=false (no image reference injected)."""
    return (
        "\n"
        + "Foobar"
        + "\n\n"
        + "HOLIDAY THEME OCR TEST\n\nENGLISH WORDS DEUTSCHE WÖRTER\nBEACH STRAND\nRELAX URLAUB\nSUMMER SONNE\n\nTRAVEL MEER"
    )


@pytest.fixture
def expected_pdf_md_header_no_refs() -> dict:
    return {
        "chunk": 1,
        "file": "00001.md",
        "languages": ["en"],
        "keywords": [
            "beach strand relax",
            "deutsche wörter beach",
            "holiday theme ocr",
            "ocr test english",
            "relax urlaub summer",
            "sonne travel meer",
            "strand relax urlaub",
            "theme ocr test",
            "urlaub summer sonne",
            "wörter beach strand",
        ],
        "pageNumber": 1,
    }


@pytest.fixture
def expected_pdf_metadata_no_refs() -> dict:
    return {
        "name": "bar.pdf",
        "size": 1216058,
        "chunks": 1,
        "mimeType": "application/pdf",
        "languages": ["en"],
        "keywords": [
            "sonne travel meer",
            "holiday theme ocr",
            "theme ocr test",
            "ocr test english",
            "deutsche wörter beach",
            "wörter beach strand",
            "beach strand relax",
            "strand relax urlaub",
            "relax urlaub summer",
            "urlaub summer sonne",
        ],
    }


def test_extract_pdf_returns_zip_no_images(
    client,
    auth_headers,
    pdf_file,
    monkeypatch,
    expected_pdf_md_content_no_refs,
    expected_pdf_md_header_no_refs,
    expected_pdf_metadata_no_refs,
    extract_zip_entries,
    assert_zip_response,
    assert_markdown,
    assert_metadata_content,
) -> None:
    """SAVE_DOCUMENT_IMAGE_REFS=false: figures are omitted from the zip and no
    image references are injected into the chunks.

    Mirrors test_extract_pdf_returns_zip but with SAVE_DOCUMENT_IMAGE_REFS=false.
    OCR stays on (force_ocr), so the recognized text is still present in the
    chunks; only the image_N.webp binaries and the ``> [Image: ...]`` references
    disappear (which is why the chunk content and YAKE keywords differ slightly
    from the refs-on case).
    """
    monkeypatch.setenv("SAVE_DOCUMENT_IMAGE_REFS", "false")

    with open(pdf_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    # Key difference from test_extract_pdf_returns_zip: no image_0.webp.
    assert sorted([name for name in entries]) == sorted(
        [
            "output/chunks/00001.md",
            "output/meta.json",
        ]
    )
    assert_markdown(
        "output/chunks/00001.md",
        expected_pdf_md_content_no_refs,
        expected_pdf_md_header_no_refs,
        entries,
    )
    assert_metadata_content("output/meta.json", expected_pdf_metadata_no_refs, entries)


def test_extract_pdf_save_document_image_refs_false(
    client,
    auth_headers,
    testdata_dir,
    monkeypatch,
    extract_zip_entries,
    assert_zip_response,
) -> None:
    """SAVE_DOCUMENT_IMAGE_REFS=false on bar.pdf: no webp assets and no image
    references injected into the chunk, but OCR text is still present (force_ocr
    runs independently of image-ref injection).
    """
    monkeypatch.setenv("SAVE_DOCUMENT_IMAGE_REFS", "false")
    with open(testdata_dir / "bar.pdf", "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    # No image webp assets are written.
    assert not any(name.endswith(".webp") for name in entries)

    # The chunk carries the OCR text but no ``> [Image: ...]`` reference.
    chunk = entries["output/chunks/00001.md"].decode("utf-8")
    assert "HOLIDAY" in chunk
    assert "> [Image:" not in chunk
