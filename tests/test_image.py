import pytest


@pytest.fixture
def expected_ocr_content():
    """The expected ocr content."""
    return (
        "HOLIDAY THEME OCR TEST\n\n"
        + "WÖRTER\n\n"
        + "DEUTSCHE\n\n"
        + "ENGLISH WORDS\n\n"
        + "BEACH\n\n"
        + "STRAND\n\n"
        + "RELAX\n\n"
        + "URLAUB\n\n"
        + "SONNE\n\n"
        + "SUMMER\n\n"
        + "TRAVEL\n\n"
        + "MEER"
    )


def test_extract_image_file_file(
    client,
    auth_headers,
    image_file,
    assert_zip_response,
    extract_zip_entries,
    assert_markdownfile_content,
    expected_ocr_content,
) -> None:
    """Test that plain text is supported."""
    with open(image_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("ocr_png.png", f)},
            headers=auth_headers,
        )
    assert response.status_code == 200
    assert_zip_response(response, "foo.doc.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        [
            "output/assets/ocr_png.webp",
            "output/assets/ocr_png_ocr.md",
        ]
    )

    assert_markdownfile_content("output/assets/ocr_png_ocr.md", expected_ocr_content, entries)
