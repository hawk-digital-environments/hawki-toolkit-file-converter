import re


def test_convert_returns_job_id_with_202(client, auth_headers) -> None:
    """POST /convert returns 202 with a job_id and relative download_url."""
    resp = client.post(
        "/convert",
        files={"file": ("dedup.txt", b"first upload", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.content
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"].startswith("convert-")
    assert re.match(r"^convert-[0-9a-f-]{36}$", body["job_id"])
    assert body["download_url"] == f"/download/{body['job_id']}"


def test_convert_different_content_starts_new_job(client, auth_headers) -> None:
    """Different bytes (same filename) must start a new job."""
    a = client.post(
        "/convert",
        files={"file": ("diff.txt", b"content A", "text/plain")},
        headers=auth_headers,
    )
    b = client.post(
        "/convert",
        files={"file": ("diff.txt", b"content B", "text/plain")},
        headers=auth_headers,
    )
    assert a.status_code == 202
    assert b.status_code == 202
    assert a.json()["job_id"] != b.json()["job_id"]


def test_convert_missing_auth_returns_401(client) -> None:
    """A /convert request without auth returns 401."""
    resp = client.post(
        "/convert",
        files={"file": ("unauth.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 401


def test_convert_unsupported_file_type_returns_400(client, auth_headers) -> None:
    """An unsupported binary file returns 400 without starting a workflow."""
    binary_data = bytes(range(256))
    resp = client.post(
        "/convert",
        files={
            "file": (
                "foo.unknown",
                binary_data,
                "application/octet-stream",
            )
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_convert_missing_filename_returns_422(client, auth_headers) -> None:
    """Empty filename is rejected by the multipart parser as 422."""
    resp = client.post(
        "/convert",
        files={"file": ("", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code in (400, 422)


def test_convert_workflow_completes_and_zip_exists(convert_and_wait, auth_headers, client) -> None:
    """End-to-end: /convert starts a workflow that finishes with a zip on disk."""
    convert_resp, detail = convert_and_wait(b"hello world end-to-end", "e2e.txt")
    job_id = convert_resp.json()["job_id"]

    assert detail["status_detail"]["status"] == "completed"
    assert detail["status"] == "COMPLETED"
    assert detail["job_id"] == job_id

    # The zip should be on disk under SHARED_TMP / job_id / result / output.zip
    from main import job_zip_path

    assert job_zip_path(job_id).exists(), "zip was not written"
