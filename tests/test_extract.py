import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
import json
import pytest
import logging
from httpx import Response

logger = logging.getLogger(__name__)


@pytest.fixture
def save_debug_zip() -> Callable[[Response, Path | None, str], None]:
    """Return a helper that saves response content to a debug directory."""

    def _save_debug_zip(
        response: Response, debug_dir: Path | None, filename: str
    ) -> None:
        if debug_dir is None:
            return
        dest = debug_dir / filename
        dest.write_bytes(response.content)
        logger.info(f"DEBUG_ZIP: saved to {dest}")

    return _save_debug_zip


@pytest.fixture
def extract_zip_entries() -> Callable[[Response], dict[str, bytes]]:
    """Return a helper that extracts zip entries from a response."""

    def _extract_zip_entries(response: Response) -> dict[str, bytes]:
        buf = io.BytesIO(response.content)
        with zipfile.ZipFile(buf) as z:
            return {
                name: z.read(name) for name in z.namelist() if not name.endswith("/")
            }

    return _extract_zip_entries


@pytest.fixture
def assert_zip_response(
    save_debug_zip, debug_zip
) -> Callable[[Response, Path | None, str], None]:
    """Return a helper that asserts a response is a valid zip download."""

    def _assert_zip_response(
        response: Response, zip_filename: str
    ) -> None:
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert zipfile.is_zipfile(io.BytesIO(response.content))

        save_debug_zip(response, debug_zip, zip_filename)

    return _assert_zip_response


@pytest.fixture
def assert_markdownfile_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts markdown file content matches expected."""

    def _assert_markdownfile_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = entries[actual_path].decode("utf-8")
        actual = re.sub(r"/tmp/tmp[^/]+/", "/tmp/tmpXXXXXX/", actual)

        assert actual == expected_content, (
            f"Markdown content mismatch for {actual_path}.\n"
        )
        assert actual == expected_content
    return _assert_markdownfile_content


@pytest.fixture
def assert_metadata_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts metadata file content matches expected."""

    def _assert_metadata_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = json.loads(entries[actual_path].decode("utf-8"))
        assert actual == expected_content, (
            f"Metadata content mismatch for {actual_path}.\n"
        )

    return _assert_metadata_content

def test_extract_pdf_returns_zip(
    client,
    auth_headers,
    pdf_file,
    expected_pdf_md,
    extract_zip_entries,
    assert_markdownfile_content,
    assert_zip_response,
    expected_pdf_metadata,
    assert_metadata_content
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

    assert sorted([name for name in entries]) == sorted([
        "output/content_markdown.md",
        "output/image_0.jpeg",
        "output/image_0_ocr.md",
        "output/metadata.md"
    ])
    assert_markdownfile_content("output/content_markdown.md", expected_pdf_md, entries)
    assert_metadata_content("output/metadata.md", expected_pdf_metadata, entries)


def test_extract_doc_returns_zip(
    client,
    auth_headers,
    doc_file,
    expected_doc_md,
    assert_markdownfile_content,
    extract_zip_entries,
    assert_zip_response,
    expected_docx_metadata,
    assert_metadata_content
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

    assert sorted([name for name in entries]) == sorted([
        "output/content_markdown.md",
        "output/image_0.png",
        "output/image_0_ocr.md",
        "output/metadata.md"
    ])
    assert_markdownfile_content("output/content_markdown.md", expected_doc_md, entries)
    assert_metadata_content("output/metadata.md", expected_docx_metadata, entries)


def test_extract_missing_auth_returns_401(client) -> None:
    """Test that a request without auth returns 401."""
    response = client.post(
        "/extract",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401, response.content


def test_extract_unsupported_file_type_returns_400(client, auth_headers) -> None:
    """Test that posting an unsupported file type returns 500."""
    response = client.post(
        "/extract",
        files={"file": ("foo.bar", b"some content", "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type `.bar`. Supported types: .7z, .bib, .bmp, .commonmark, .csv, .dbf, .dbk, .djot, .doc, .docbook, .docbook4, .docbook5, .docm, .docx, .dot, .dotm, .dotx, .eml, .enw, .epub, .fb2, .gif, .gz, .htm, .html, .hwp, .hwpx, .ipynb, .j2c, .j2k, .jats, .jb2, .jbig2, .jp2, .jpeg, .jpg, .jpm, .jpx, .json, .jsonl, .key, .latex, .markdown, .md, .mdx, .mj2, .msg, .nbib, .ndjson, .numbers, .ods, .odt, .opml, .org, .pages, .pbm, .pdf, .pgm, .png, .pnm, .pot, .potm, .potx, .ppm, .ppsx, .ppt, .pptm, .pptx, .pst, .ris, .rst, .rtf, .svg, .tar, .tex, .tgz, .tif, .tiff, .toml, .tsv, .txt, .typ, .typst, .webp, .xla, .xlam, .xls, .xlsb, .xlsm, .xlsx, .xlt, .xltx, .xml, .yaml, .yml, .zip"

def test_extract_text_file(
    client, auth_headers, assert_zip_response, extract_zip_entries, assert_markdownfile_content, assert_metadata_content
) -> None:
    """Test that plain text is supported."""
    response = client.post(
        "/extract",
        files={"file": ("baz.txt", b"hello world", "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "foo.doc.zip")
    entries = extract_zip_entries(response)
    
    assert sorted([name for name in entries]) == sorted([
        "output/content_markdown.md",
        "output/metadata.md"
    ])
    
    assert_markdownfile_content("output/content_markdown.md", "hello world\n", entries)
    assert_metadata_content(
        "output/metadata.md", 
        {
            "character_count": 11,
            "format_type": "text",
            "line_count": 1,
            "word_count": 2,
        },
        entries
    )
