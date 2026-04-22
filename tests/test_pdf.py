import pytest
from pathlib import Path


@pytest.fixture
def pdf_file(testdata_dir) -> Path:
    """Return the path to the sample PDF test file."""
    path = testdata_dir / "same_origin_export_to_pdf_and_doc.pdf"
    return path


@pytest.fixture
def expected_pdf_md_content() -> str:
    """Return the expected markdown content from PDF extraction."""
    return (
        "\n\n"
        + "> [Image: ../assets/image_0.webp]\n"
        + "> HOLIDAY THEME OCR TEST || WÖRTER || DEUTSCHE || ENGLISH WORDS || BEACH || STRAND || RELAX || URLAUB || SONNE || SUMMER || TRAVEL || MEER\n"
        + "Foobar"
    )


@pytest.fixture
def expected_pdf_md_header() -> dict:
    """Return the expected PDF header in markdown."""
    return {
        "chunk": 1,
        "file": "00001.md",
        "keywords": [
            "deutsche",
            "holiday theme",
            "holiday theme ocr",
            "holiday theme ocr test",
            "image",
            "meer foobar",
            "ocr test",
            "theme ocr",
            "theme ocr test",
            "wörter",
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
        "languages": ["eng"],
        "keywords": [
             "deutsche",
            "holiday theme",
            "holiday theme ocr",
            "holiday theme ocr test",
            "image",
            "meer foobar",
            "ocr test",
            "theme ocr",
            "theme ocr test",
            "wörter",
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
            "output/assets/image_0_ocr.md",
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
