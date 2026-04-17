import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app  # noqa: E402

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
def pdf_file(testdata_dir) -> Path:
    """Return the path to the sample PDF test file."""
    path = testdata_dir / "bar.pdf"
    return path


@pytest.fixture
def doc_file(testdata_dir) -> Path:
    """Return the path to the sample DOCX test file."""
    path = testdata_dir / "foo.docx"
    return path


@pytest.fixture
def expected_pdf_md() -> str:
    """Return the expected markdown content from PDF extraction."""
    return "# Chunk 1-1\n\n## Page 1\n\nfoobar\n\n![p1](/images_pdf/c0_p1_i1.jpeg)"


@pytest.fixture
def expected_doc_md() -> str:
    """Return the expected markdown content from DOCX extraction."""
    return (
        "foobar\n\n"
        "![](/tmp/tmpXXXXXX/output/media/image1.png)"
        '{width="6.6930555555555555in" height="6.6930555555555555in"}\n'
    )


@pytest.fixture
def debug_zip(request, tmp_path) -> Path | None:
    """Create a debug zip output directory when DEBUG_ZIP env var is set."""
    if not os.getenv("DEBUG_ZIP"):
        return None
    out = tmp_path / "debug_zips" / request.node.name
    out.mkdir(parents=True, exist_ok=True)
    return out
