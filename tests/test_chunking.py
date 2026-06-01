import pytest
from pathlib import Path


@pytest.fixture
def file_to_test_chunks(testdata_dir) -> Path:
    path = testdata_dir / "abcdefghij.pdf"
    return path


@pytest.fixture
def chunk_env_1(monkeypatch):
    monkeypatch.setenv("MAX_CHUNK_LENGTH", str(1))


@pytest.mark.usefixtures("chunk_env_1")
def test_chunk_with_1(
    client,
    auth_headers,
    file_to_test_chunks,
    extract_zip_entries,
    assert_zip_response,
    assert_metadata_content,
    assert_markdown,
) -> None:
    with open(file_to_test_chunks, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        [
            "output/chunks/00001.md",
            "output/chunks/00002.md",
            "output/chunks/00003.md",
            "output/chunks/00004.md",
            "output/chunks/00005.md",
            "output/chunks/00006.md",
            "output/chunks/00007.md",
            "output/chunks/00008.md",
            "output/chunks/00009.md",
            "output/chunks/00010.md",
            "output/meta.json",
        ]
    )
    letters = "abcdefghij"
    for md_num in range(1, 10):
        assert_markdown(
            f"output/chunks/0000{md_num}.md",
            f"\n{letters[md_num-1]}",
            {
                "chunk": md_num,
                "file": f"0000{md_num}.md",
                "nextChunk": f"{(md_num+1):05d}.md",
                "pageNumber": 1,
            },
            entries,
        )
    assert_markdown(
        f"output/chunks/00010.md",
        f"\nj",
        {
            "chunk": 10,
            "file": f"00010.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_metadata_content(
        "output/meta.json",
        {
            "chunks": 10,
            "languages": [
                "de",
            ],
            "mimeType": "application/pdf",
            "name": "bar.pdf",
            "size": 590,
        },
        entries,
    )


@pytest.fixture
def chunk_env_2(monkeypatch):
    monkeypatch.setenv("MAX_CHUNK_LENGTH", str(2))

@pytest.mark.usefixtures("chunk_env_2")
def test_chunk_with_2(
    client,
    auth_headers,
    file_to_test_chunks,
    extract_zip_entries,
    assert_zip_response,
    assert_metadata_content,
    assert_markdown,
) -> None:
    with open(file_to_test_chunks, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        [
            "output/chunks/00001.md",
            "output/chunks/00002.md",
            "output/chunks/00003.md",
            "output/chunks/00004.md",
            "output/chunks/00005.md",
            "output/meta.json",
        ]
    )
    assert_markdown(
        f"output/chunks/00001.md",
        f"\nab",
        {
            "chunk": 1,
            "file": "00001.md",
            "nextChunk": "00002.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00002.md",
        f"\ncd",
        {
            "chunk": 2,
            "file": "00002.md",
            "nextChunk": "00003.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00003.md",
        f"\nef",
        {
            "chunk": 3,
            "file": "00003.md",
            "nextChunk": "00004.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00004.md",
        f"\ngh",
        {
            "chunk": 4,
            "file": "00004.md",
            "nextChunk": "00005.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00005.md",
        f"\nij",
        {
            "chunk": 5,
            "file": f"00005.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_metadata_content(
        "output/meta.json",
        {
            "chunks": 5,
            "languages": [
                "de",
            ],
            "mimeType": "application/pdf",
            "name": "bar.pdf",
            "size": 590,
        },
        entries,
    )


@pytest.fixture
def chunk_env_3(monkeypatch):
    monkeypatch.setenv("MAX_CHUNK_LENGTH", str(3))

@pytest.mark.usefixtures("chunk_env_3")
def test_chunk_with_3(
    client,
    auth_headers,
    file_to_test_chunks,
    extract_zip_entries,
    assert_zip_response,
    assert_metadata_content,
    assert_markdown,
) -> None:
    with open(file_to_test_chunks, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("bar.pdf", f, "application/pdf")},
            headers=auth_headers,
        )

    assert_zip_response(response, "bar.pdf.zip")
    entries = extract_zip_entries(response)

    assert sorted([name for name in entries]) == sorted(
        [
            "output/chunks/00001.md",
            "output/chunks/00002.md",
            "output/chunks/00003.md",
            "output/chunks/00004.md",
            "output/meta.json",
        ]
    )
    assert_markdown(
        f"output/chunks/00001.md",
        f"\nabc",
        {
            "chunk": 1,
            "file": "00001.md",
            "nextChunk": "00002.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00002.md",
        f"\ndef",
        {
            "chunk": 2,
            "file": "00002.md",
            "nextChunk": "00003.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00003.md",
        f"\nghi",
        {
            "chunk": 3,
            "file": "00003.md",
            "nextChunk": "00004.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_markdown(
        f"output/chunks/00004.md",
        f"\nj",
        {
            "chunk": 4,
            "file": "00004.md",
            "pageNumber": 1,
        },
        entries,
    )
    assert_metadata_content(
        "output/meta.json",
        {
            "chunks": 4,
            "languages": [
                "de",
            ],
            "mimeType": "application/pdf",
            "name": "bar.pdf",
            "size": 590,
        },
        entries,
    )
