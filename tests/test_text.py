import pytest


def test_extract_text_file(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
    assert_markdownfile_content,
    assert_metadata_content,
) -> None:
    """Test that plain text is supported."""
    response = client.post(
        "/extract",
        files={"file": ("baz.txt", b"hello world", "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "foo.doc.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        ["output/chunks/00001.md", "output/meta.json"]
    )

    assert_markdownfile_content(
        "output/chunks/00001.md",
        ("---\n" + "file: 00001.md\n" + "chunk: 1\n" + "---\n\n" + "hello world"),
        entries,
    )
    assert_metadata_content(
        "output/meta.json",
        {
            "chunks": 1,
            "languages": [
                "en",
            ],
            "mimeType": "text/plain",
            "name": "baz.txt",
            "size": 11,
        },
        entries,
    )


@pytest.mark.parametrize(
    "expected_filename",
    [
        "täst öäü.txt",
        "my file.txt",
        "Müller Datei (1).txt",
        "文件.txt",
        "\U0001f4c4dokument.txt",
        "café résumé.txt",
    ],
    ids=[
        "umlauts",
        "spaces",
        "umlauts_spaces_parens",
        "cjk",
        "emoji",
        "accented",
    ],
)
def test_extract_text_file_special_filenames(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
    assert_metadata_content,
    expected_filename,
) -> None:
    """Test that filenames with special characters are handled correctly."""
    content = b"hello special chars"
    response = client.post(
        "/extract",
        files={"file": (expected_filename, content, "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "special.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        ["output/chunks/00001.md", "output/meta.json"]
    )
    assert_metadata_content(
        "output/meta.json",
        {
            "chunks": 1,
            "languages": [
                "en",
            ],
            "mimeType": "text/plain",
            "name": expected_filename,
            "size": len(content),
        },
        entries,
    )


def test_extract_binary_unknown_extension_rejected(
    client,
    auth_headers,
) -> None:
    """Test that a binary file with unknown extension is still rejected."""
    binary_data = bytes(range(256))
    response = client.post(
        "/extract",
        files={"file": ("data.bin", binary_data, "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]