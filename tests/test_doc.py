from pathlib import Path

import pytest


@pytest.fixture
def doc_file(testdata_dir) -> Path:
    """Return the path to the sample PDF test file."""
    path = testdata_dir / "same_origin_export_to_pdf_and_doc.docx"
    return path


@pytest.fixture
def expected_doc_md_content() -> str:
    """Return the expected markdown content from PDF extraction."""
    return (
        "\n\n> [Image: ../assets/image_0.webp]\n"
        "Foobar\n\n"
        "HOLIDAY THEME OCR TEST\n\n"
        "ENGLISH WORDS DEUTSCHE WÖRTER\n"
        "BEACH STRAND\n"
        "RELAX URLAUB\n"
        "SUMMER SONNE\n\n"
        "TRAVEL MEER"
    )


@pytest.fixture
def expected_docx_metadata() -> dict:
    """Return the expected PDF metadata."""
    return {
        "name": "foo.docx",
        "size": 1485543,
        "chunks": 1,
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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


@pytest.fixture
def expected_doc_md_header() -> dict:
    return {
        "file": "00001.md",
        "chunk": 1,
        "languages": ["en"],
        "pageNumber": 1,
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
    }


def test_extract_doc_returns_zip(
    client,
    auth_headers,
    doc_file,
    expected_doc_md_content,
    assert_markdown,
    extract_zip_entries,
    assert_zip_response,
    expected_docx_metadata,
    assert_metadata_content,
    expected_doc_md_header,
) -> None:
    """Test that posting a DOCX returns a valid zip with markdown and images."""
    with open(doc_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("foo.docx", f, "application/msword")},
            headers=auth_headers,
        )

    assert_zip_response(response, "foo.doc.zip")
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
        expected_doc_md_content,
        expected_doc_md_header,
        entries,
    )
    assert_metadata_content("output/meta.json", expected_docx_metadata, entries)
