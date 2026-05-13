import pytest


@pytest.fixture
def expected_formats() -> set[str]:
    """A list of supported formats"""
    return {
        ".7z",
        ".bib",
        ".bmp",
        ".commonmark",
        ".csv",
        ".dbf",
        ".dbk",
        ".djot",
        ".doc",
        ".docbook",
        ".docbook4",
        ".docbook5",
        ".docm",
        ".docx",
        ".dot",
        ".dotm",
        ".dotx",
        ".eml",
        ".enw",
        ".epub",
        ".fb2",
        ".gif",
        ".gz",
        ".htm",
        ".html",
        ".hwp",
        ".hwpx",
        ".ipynb",
        ".j2c",
        ".j2k",
        ".jats",
        ".jb2",
        ".jbig2",
        ".jp2",
        ".jpeg",
        ".jpg",
        ".jpm",
        ".jpx",
        ".json",
        ".jsonl",
        ".key",
        ".latex",
        ".markdown",
        ".md",
        ".mdx",
        ".mj2",
        ".msg",
        ".nbib",
        ".ndjson",
        ".numbers",
        ".ods",
        ".odt",
        ".opml",
        ".org",
        ".pages",
        ".pbm",
        ".pdf",
        ".pgm",
        ".png",
        ".pnm",
        ".pot",
        ".potm",
        ".potx",
        ".ppm",
        ".ppsx",
        ".ppt",
        ".pptm",
        ".pptx",
        ".pst",
        ".ris",
        ".rst",
        ".rtf",
        ".svg",
        ".tar",
        ".tex",
        ".tgz",
        ".tif",
        ".tiff",
        ".toml",
        ".tsv",
        ".txt",
        ".typ",
        ".typst",
        ".webp",
        ".xla",
        ".xlam",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
        ".xlt",
        ".xltx",
        ".xml",
        ".yaml",
        ".yml",
        ".zip",
    }


@pytest.fixture
def expected_image_formats() -> set[str]:
    """The expected image formats."""
    return {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
        ".jp2",
        ".j2k",
        ".jpx",
        ".jpm",
        ".mj2",
        ".pbm",
        ".pgm",
        ".ppm",
        ".pnm",
    }


def test_root_returns_service_info(
    client, auth_headers, expected_formats, expected_image_formats
) -> None:
    """Test that GET / returns service info with supported formats and endpoints."""
    response = client.get("/", headers=auth_headers)

    assert response.status_code == 200

    body = response.json()
    assert body["service"] == "File to Markdown Converter"

    assert body["auth"] == "Bearer token required"
    assert (
        len(expected_formats.difference(body["supported_formats"])) == 0
    ), f"Unexpected supported format {expected_formats.difference(body["supported_formats"])}"
    assert (
        len(expected_image_formats.difference(body["image_formats"])) == 0
    ), f"Unexpected supported image format {expected_image_formats.difference(body["supported_formats"])}"

    assert body["endpoints"] == {
        "/extract": "POST - Upload file for conversion",
        "/": "GET - This info page",
    }


def test_root_missing_auth_returns_401(client) -> None:
    """Test that GET / without auth returns 401."""
    response = client.get("/")
    assert response.status_code == 401


def test_root_invalid_key_returns_401(client) -> None:
    """Test that GET / with wrong key returns 401."""
    response = client.get("/", headers={"Authorization": "Bearer wrong-key"})
    assert response.status_code == 401
