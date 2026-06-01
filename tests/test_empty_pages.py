import pytest
from pathlib import Path


@pytest.fixture
def doc_file(testdata_dir, file_name) -> Path:
    """Return the path to the sample PDF test file."""
    path = testdata_dir / file_name
    return path


@pytest.fixture
def expected_doc_md_content() -> str:
    """Return the expected markdown content from PDF extraction."""
    return "\nThis is a Heading 1\nHello world"


@pytest.fixture
def expected_docx_metadata(expected_size) -> dict:
    """Return the expected PDF metadata."""
    return {
        "name": "foo.docx",
        "size": expected_size,
        "chunks": 1,
        "createdAt": "2000-01-01T00:00:00Z",
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "languages": ["de"],
    }


@pytest.fixture
def expected_doc_md_header() -> dict:
    return {
        "file": "00001.md",
        "chunk": 1,
        "keywords": [],
    }


@pytest.mark.parametrize(
    "file_name, expected_size",
    [
        ["content_on_page_1_of_3.docx", 36647],
        ["content_on_page_2_of_3.docx", 36652],
        ["content_on_page_3_of_3.docx", 36651],
    ],
)
def test_doc_with_empty_pages_extracts_single_md(
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
    """Test that posting a DOCX with empty pages returns a valid zip with markdown and single chunk."""
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
