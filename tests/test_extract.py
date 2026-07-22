import logging

logger = logging.getLogger(__name__)


def test_extract_missing_auth_returns_401(client) -> None:
    """Test that a request without auth returns 401."""
    response = client.post(
        "/extract",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401, response.content


def test_extract_unsupported_file_type_returns_400(client, auth_headers) -> None:
    """Test that posting a binary file with unknown extension returns 400."""
    binary_data = bytes(range(256))
    response = client.post(
        "/extract",
        files={"file": ("foo.bar", binary_data, "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
