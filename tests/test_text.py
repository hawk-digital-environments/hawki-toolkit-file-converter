import re

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


def test_extract_strips_stray_control_chars_from_output(
    client,
    auth_headers,
    assert_zip_response,
    extract_zip_entries,
) -> None:
    """Stray control characters (e.g. STX/0x02 leaked by PDF text-layer extraction)
    must not leak into the output markdown, where they make MIME sniffers classify
    the whole file as application/octet-stream instead of text/plain."""
    response = client.post(
        "/extract",
        files={"file": ("ctrl.txt", b"hello\x02world", "text/plain")},
        headers=auth_headers,
    )
    assert_zip_response(response, "ctrl.zip")
    entries = extract_zip_entries(response)

    text = entries["output/chunks/00001.md"].decode("utf-8")

    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]", text)
    assert "hello" in text
    assert "world" in text
