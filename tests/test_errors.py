from unittest.mock import patch, AsyncMock, MagicMock


def _make_result_with_broken_image() -> MagicMock:
    result = MagicMock()
    result.content = ""
    result.elements = [
        {
            "element_type": "image",
            "text": "",
            "metadata": {"page_number": 1},
        }
    ]
    result.images = []
    result.pages = 1
    result.mime_type = "application/pdf"
    result.detected_languages = ["de"]
    return result


def test_runtime_error_returns_400_with_message(client, auth_headers) -> None:
    mock_result = _make_result_with_broken_image()
    with patch("utils.processor.extract_file", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_result
        response = client.post(
            "/extract",
            files={"file": ("broken.pdf", b"fake pdf", "application/pdf")},
            headers=auth_headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Images cannot be extracted for this document."
