import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import json
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
    return "\\--- Page 1 ---\n\nFoobar\n\nHOLIDAY THEME OCR TEST\n\nDEUTSCHE WÖRTER\n\nENGLISH WORDS\n\nBEACH\n\nSTRAND\n\nURLAUB\n\nRELAX\n\nSONNE\n\nSUMMER\n\nMEER\n\nTRAVEL\n"


@pytest.fixture
def expected_pdf_metadata()-> str:
    """Return the expected PDF metadata."""
    return json.loads('{\n  "created_at": "2026-04-20T09:09:30Z",\n  "created_by": "Writer",\n  "pages": {\n    "total_count": 1,\n    "unit_type": "page",\n    "boundaries": [\n      {\n        "byte_start": 18,\n        "byte_end": 24,\n        "page_number": 1\n      }\n    ],\n    "pages": [\n      {\n        "number": 1,\n        "dimensions": [\n          595.303955078125,\n          841.8897705078125\n        ],\n        "is_blank": false\n      }\n    ]\n  },\n  "format_type": "pdf",\n  "pdf_version": "1.7",\n  "producer": "LibreOffice 25.8.6.2 (X86_64) / LibreOffice Community",\n  "is_encrypted": false,\n  "width": 595,\n  "height": 842,\n  "page_count": 1\n}')


@pytest.fixture
def expected_doc_md() -> str:
    """Return the expected markdown content from DOCX extraction."""
    return (
        "Foobar\n\n"
        "![](image_0.png)\n"
    )


@pytest.fixture
def doc_file(testdata_dir) -> Path:
    """Return the path to the sample DOCX test file."""
    path = testdata_dir / "foo.docx"
    return path


@pytest.fixture
def expected_docx_metadata()-> str:
    """Return the expected DOCX metadata."""
    return json.loads('{\n  "language": "de-DE",\n  "created_at": "2026-04-20T09:01:14Z",\n  "modified_at": "2026-04-20T09:02:58Z",\n  "format_type": "docx",\n  "core_properties": {\n    "title": null,\n    "subject": null,\n    "creator": null,\n    "keywords": null,\n    "description": null,\n    "last_modified_by": null,\n    "revision": "1",\n    "created": "2026-04-20T09:01:14Z",\n    "modified": "2026-04-20T09:02:58Z",\n    "category": null,\n    "content_status": null,\n    "language": "de-DE",\n    "identifier": null,\n    "version": null,\n    "last_printed": "2026-04-20T09:09:30Z"\n  },\n  "app_properties": {\n    "application": "LibreOffice/25.8.6.2$Linux_X86_64 LibreOffice_project/a46b460d1686bb49c718d2ef5f88b83ff2dc4981",\n    "app_version": "15.0000",\n    "template": null,\n    "total_time": 0,\n    "pages": 1,\n    "words": 1,\n    "characters": 6,\n    "characters_with_spaces": 6,\n    "lines": null,\n    "paragraphs": 1,\n    "company": null,\n    "doc_security": null,\n    "scale_crop": null,\n    "links_up_to_date": null,\n    "shared_doc": null,\n    "hyperlinks_changed": null\n  },\n  "custom_properties": {},\n  "character_count": 6,\n  "total_editing_time_minutes": 0,\n  "word_count": 1,\n  "paragraph_count": 1,\n  "page_count": 1,\n  "application": "LibreOffice/25.8.6.2$Linux_X86_64 LibreOffice_project/a46b460d1686bb49c718d2ef5f88b83ff2dc4981",\n  "revision": "1"\n}')


@pytest.fixture
def debug_zip(request, tmp_path) -> Path:
    """Create a debug zip output directory when DEBUG_ZIP env var is set."""
    if not os.getenv("DEBUG_ZIP"):
        return None
    out = tmp_path / "debug_zips" / request.node.name
    out.mkdir(parents=True, exist_ok=True)
    return out
