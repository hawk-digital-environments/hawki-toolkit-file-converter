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
                "de",
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
                "de",
            ],
            "mimeType": "text/plain",
            "name": expected_filename,
            "size": len(content),
        },
        entries,
    )


def test_extract_python_file_text_fallback(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
    assert_markdownfile_content,
) -> None:
    """Test that .py files are accepted via text fallback."""
    code = b'def hello():\n    print("Hello, world!")\n'
    response = client.post(
        "/extract",
        files={"file": ("script.py", code, "text/x-python")},
        headers=auth_headers,
    )
    assert_zip_response(response, "script.py.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        ["output/chunks/00001.md", "output/meta.json"]
    )
    assert_markdownfile_content(
        "output/chunks/00001.md",
        '---\nfile: 00001.md\nchunk: 1\n---\n\ndef hello():\n    print("Hello, world!")\n',
        entries,
    )

    import json

    meta = json.loads(entries["output/meta.json"])
    assert "text/plain" in meta["mimeType"]
    assert meta["name"] == "script.py"
    assert meta["size"] == len(code)


def test_extract_no_extension_text_fallback(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
) -> None:
    """Test that a text file with no extension is accepted via fallback."""
    content = b"Dockerfile content goes here\n"
    response = client.post(
        "/extract",
        files={"file": ("Dockerfile", content, "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "Dockerfile.zip")
    entries = extract_zip_entries(response)
    assert "output/chunks/00001.md" in entries
    assert "output/meta.json" in entries


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


def test_extract_path_traversal_filename_sanitized(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
) -> None:
    """Test that path traversal in filename is sanitized to basename only."""
    response = client.post(
        "/extract",
        files={"file": ("../../../etc/passwd", b"root:x:0:0", "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "passwd.zip")
    entries = extract_zip_entries(response)
    import json

    meta = json.loads(entries["output/meta.json"])
    assert meta["name"] == "passwd"


def test_extract_null_byte_filename_handled(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
) -> None:
    """Test that null-byte-like sequences in filename are handled safely.

    The HTTP test client URL-encodes \\x00 to %00, so the filename
    arrives as literal characters (not an actual null byte). The file
    should still be processed safely without path issues.
    """
    response = client.post(
        "/extract",
        files={"file": ("test\x00.py", b"print(1)", "text/plain")},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_text_fallback_disabled_rejects_py_file(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """Test that .py files are rejected when USE_TEXT_FALLBACK is false."""
    monkeypatch.setattr("main.USE_TEXT_FALLBACK", False)
    response = client.post(
        "/extract",
        files={"file": ("script.py", b'print("hello")', "text/x-python")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
