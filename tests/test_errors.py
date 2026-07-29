from unittest.mock import AsyncMock, MagicMock, patch


def _make_envelope_with_error() -> MagicMock:
    """xberg's extract() returns an ExtractionResult envelope; a non-empty
    errors list makes _unwrap_single raise RuntimeError, which the /extract
    handler surfaces as a 400."""
    error = MagicMock()
    error.message = "extraction failed"
    envelope = MagicMock()
    envelope.errors = [error]
    envelope.results = []
    return envelope


def test_runtime_error_returns_400_with_message(client, auth_headers) -> None:
    mock_envelope = _make_envelope_with_error()
    with patch("utils.processor.extract", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_envelope
        response = client.post(
            "/extract",
            files={"file": ("broken.pdf", b"fake pdf", "application/pdf")},
            headers=auth_headers,
        )

    assert response.status_code == 400
