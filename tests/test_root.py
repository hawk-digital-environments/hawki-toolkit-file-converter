import pytest


@pytest.fixture
def expected_formats() -> list[str]:
    """A list of supported formats"""
    return [
        ".pdf",
        ".doc",
        ".docx"
    ]


def test_root_returns_service_info(client, auth_headers, expected_formats) -> None:
    """Test that GET / returns service info with supported formats and endpoints."""
    response = client.get("/", headers=auth_headers)

    assert response.status_code == 200

    body = response.json()
    assert body["service"] == "File to Markdown Converter"
    assert body["auth"] == "X-API-KEY required"
    assert body["supported_formats"] == expected_formats
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
