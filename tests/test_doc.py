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
        "\nFoobar\n\n"
        + "> [Image: ../assets/image_0.webp]\n"
        + "> HOLIDAY THEME OCR TEST || WÖRTER || DEUTSCHE || ENGLISH WORDS || BEACH || STRAND || RELAX || URLAUB || SONNE || SUMMER || TRAVEL || MEER\n"
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
            "deutsche",
            "foobar",
            "holiday theme",
            "holiday theme ocr",
            "holiday theme ocr test",
            "image",
            "ocr test",
            "theme ocr",
            "theme ocr test",
            "wörter",
        ],
    }


@pytest.fixture
def expected_doc_md_header() -> dict:
    return {
        "file": "00001.md",
        "chunk": 1,
        "keywords": [
            "deutsche",
            "foobar",
            "holiday theme",
            "holiday theme ocr",
            "holiday theme ocr test",
            "image",
            "ocr test",
            "theme ocr",
            "theme ocr test",
            "wörter",
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
            "output/assets/image_0_ocr.md",
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
