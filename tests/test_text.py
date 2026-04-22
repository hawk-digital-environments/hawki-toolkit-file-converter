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
