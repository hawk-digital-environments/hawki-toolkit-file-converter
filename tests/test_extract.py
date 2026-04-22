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
    """Test that posting an unsupported file type returns 500."""
    response = client.post(
        "/extract",
        files={"file": ("foo.bar", b"some content", "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Unsupported file type `.bar`. Supported types: .7z, .bib, .bmp, .commonmark, .csv, .dbf, .dbk, .djot, .doc, .docbook, .docbook4, .docbook5, .docm, .docx, .dot, .dotm, .dotx, .eml, .enw, .epub, .fb2, .gif, .gz, .htm, .html, .hwp, .hwpx, .ipynb, .j2c, .j2k, .jats, .jb2, .jbig2, .jp2, .jpeg, .jpg, .jpm, .jpx, .json, .jsonl, .key, .latex, .markdown, .md, .mdx, .mj2, .msg, .nbib, .ndjson, .numbers, .ods, .odt, .opml, .org, .pages, .pbm, .pdf, .pgm, .png, .pnm, .pot, .potm, .potx, .ppm, .ppsx, .ppt, .pptm, .pptx, .pst, .ris, .rst, .rtf, .svg, .tar, .tex, .tgz, .tif, .tiff, .toml, .tsv, .txt, .typ, .typst, .webp, .xla, .xlam, .xls, .xlsb, .xlsm, .xlsx, .xlt, .xltx, .xml, .yaml, .yml, .zip"
    )
