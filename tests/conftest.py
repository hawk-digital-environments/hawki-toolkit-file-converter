import os
from collections.abc import Generator, Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fastapi.testclient import TestClient
import io
import re
import zipfile
from pathlib import Path
import json
import pytest
from httpx import Response
import logging
import re
import yaml
from collections.abc import Callable
import json

from main import app  # noqa: E402


logger = logging.getLogger(__name__)

TESTDATA_DIR = Path(__file__).parent / "testdata"
TEST_API_KEY = "test-secret-key"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """Set the api key in tests."""
    monkeypatch.setenv("F_API_KEY", TEST_API_KEY)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client for the FastAPI app."""
    with TestClient(app) as cl:
        yield cl


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return auth headers with a valid Bearer token."""
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def testdata_dir() -> Path:
    """Return the path to the testdata directory."""
    return TESTDATA_DIR


@pytest.fixture
def image_file(testdata_dir) -> Path:
    """Return the path to the sample image test file."""
    path = testdata_dir / "images" / "ocr_png.png"
    return path


@pytest.fixture
def debug_zip(request, tmp_path) -> Path:
    """Create a debug zip output directory when DEBUG_ZIP env var is set."""
    if not os.getenv("DEBUG_ZIP"):
        return None
    out = tmp_path / "debug_zips" / request.node.name
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def assert_zip_response(
    save_debug_zip, debug_zip
) -> Callable[[Response, Path | None, str], None]:
    """Return a helper that asserts a response is a valid zip download."""

    def _assert_zip_response(response: Response, zip_filename: str) -> None:
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert zipfile.is_zipfile(io.BytesIO(response.content))

        save_debug_zip(response, debug_zip, zip_filename)

    return _assert_zip_response


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
def assert_metadata_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts metadata file content matches expected."""

    def _assert_metadata_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = json.loads(entries[actual_path].decode("utf-8"))
        assert (
            actual == expected_content
        ), f"Metadata content mismatch for {actual_path}.\n"

    return _assert_metadata_content


@pytest.fixture
def assert_markdownfile_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts markdown file content matches expected."""

    def _assert_markdownfile_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = entries[actual_path].decode("utf-8")
        actual = re.sub(r"/tmp/tmp[^/]+/", "/tmp/tmpXXXXXX/", actual)

        assert (
            actual == expected_content
        ), f"Markdown content mismatch for {actual_path}.\n"
        assert actual == expected_content

    return _assert_markdownfile_content


@pytest.fixture
def assert_markdown() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts markdown file content and header matches expected."""

    def extract_header_and_content(text):
        match = re.search(r"---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
        if not match:
            return None, text  # no header → whole text is content

        header_text = match.group(1)
        content = match.group(2)

        data = yaml.safe_load(header_text)

        return data, content

    def _assert_markdown(
        actual_path: str,
        expected_content: str,
        expected_header: dict,
        entries: dict[str, bytes],
    ) -> None:
        actual = entries[actual_path].decode("utf-8")
        header, content = extract_header_and_content(actual)
        if "keywords" in expected_header and( val := expected_header.pop("keywords")):
            assert sorted(val) == sorted(header.pop("keywords"))
        assert header == expected_header
        assert (
            content == expected_content
        ), f"Markdown content mismatch for {actual_path}.\n"
        assert content == expected_content

    return _assert_markdown