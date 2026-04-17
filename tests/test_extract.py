import io
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

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
    save_debug_zip,
) -> Callable[[Response, Path | None, str], None]:
    """Return a helper that asserts a response is a valid zip download."""

    def _assert_zip_response(
        response: Response, debug_zip_dir: Path | None, zip_filename: str
    ) -> None:
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert zipfile.is_zipfile(io.BytesIO(response.content))

        save_debug_zip(response, debug_zip_dir, zip_filename)

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
            f"Actual content:\n{actual}\n"
            f"Expected content:\n{expected_content}"
        )

    return _assert_markdownfile_content


def test_extract_pdf_returns_zip(
    client,
    auth_headers,
    pdf_file,
    debug_zip,
    expected_pdf_md,
    extract_zip_entries,
    assert_markdownfile_content,
    assert_zip_response,
) -> None:
    """Test that posting a PDF returns a valid zip with markdown and images."""
    with open(pdf_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, debug_zip, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    assert set(entries.keys()) == {
        "output/content_markdown.md",
        "output/images_pdf/c0_p1_i1.jpeg",
    }
    assert_markdownfile_content("output/content_markdown.md", expected_pdf_md, entries)


def test_extract_doc_returns_zip(
    client,
    auth_headers,
    doc_file,
    debug_zip,
    expected_doc_md,
    assert_markdownfile_content,
    extract_zip_entries,
    assert_zip_response,
) -> None:
    """Test that posting a DOCX returns a valid zip with markdown and images."""
    with open(doc_file, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("foo.docx", f, "application/msword")},
            headers=auth_headers,
        )

    assert_zip_response(response, debug_zip, "foo.doc.zip")
    entries = extract_zip_entries(response)

    assert set(entries.keys()) == {
        "output/content_markdown.md",
        "output/images_word/image1.png",
    }
    assert_markdownfile_content("output/content_markdown.md", expected_doc_md, entries)


def test_extract_missing_auth_returns_401(client) -> None:
    """Test that a request without auth returns 401."""
    response = client.post(
        "/extract",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401


def test_extract_unsupported_file_returns_400(
    client, auth_headers
) -> None:
    """Test that an unsupported file type returns 400."""
    response = client.post(
        "/extract",
        files={"file": ("baz.txt", b"hello world", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]
