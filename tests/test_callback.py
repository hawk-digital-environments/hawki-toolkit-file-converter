import time


def test_callback_fires_on_completion(
    convert_and_wait, callback_receiver, client, auth_headers
) -> None:
    """When a callback_url is supplied, the workflow POSTs to it on completion."""
    convert_resp, _ = convert_and_wait(
        b"callback payload",
        "cb.txt",
        callback_url=callback_receiver.url,
    )
    job_id = convert_resp.json()["job_id"]

    posts = callback_receiver.wait_for(count=1, timeout=30)
    assert len(posts) == 1, f"expected 1 callback, got {posts}"
    body, _headers = posts[0]
    assert body["job_id"] == job_id
    assert body["status"] == "completed"
    assert body["download_url"] == f"/download/{job_id}"


def test_callback_payload_download_url_is_relative(convert_and_wait, callback_receiver) -> None:
    """The callback payload always carries a relative /download/<id> URL."""
    convert_resp, _ = convert_and_wait(
        b"relative url check",
        "rel.txt",
        callback_url=callback_receiver.url,
    )
    job_id = convert_resp.json()["job_id"]

    posts = callback_receiver.wait_for(count=1, timeout=30)
    body, _ = posts[0]
    assert body["download_url"] == f"/download/{job_id}"
    assert body["download_url"].startswith("/download/")


def test_callback_retried_on_5xx(callback_receiver, client, auth_headers) -> None:
    """The callback activity retries while the receiver returns 5xx.

    We keep the receiver at 500 long enough to collect at least one failed
    POST, then flip it to 200. The workflow should subsequently complete and
    we should have observed at least two POSTs.
    """
    callback_receiver.set_status(500)

    resp = client.post(
        "/convert",
        files={"file": ("retry.txt", b"retry payload", "text/plain")},
        data={"callback_url": callback_receiver.url},
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.content
    job_id = resp.json()["job_id"]

    # Wait for at least one failed POST to land on the receiver.
    first_batch = callback_receiver.wait_for(count=1, timeout=30)
    assert len(first_batch) >= 1

    # Now allow the next retry to succeed.
    callback_receiver.set_status(200)

    # Wait until the workflow reports completed.
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        detail = client.get(f"/jobs/{job_id}", headers=auth_headers)
        if detail.status_code == 200:
            final_status = detail.json().get("status_detail", {}).get("status")
            if final_status in ("completed", "failed"):
                break
        time.sleep(0.5)

    assert final_status == "completed", (
        f"workflow did not complete after 5xx recovery (final={final_status})"
    )

    # We should have observed at least one 5xx attempt and one successful POST.
    all_posts = callback_receiver.posts
    assert len(all_posts) >= 2, (
        f"expected at least 2 callback POSTs (1 retry + 1 ok), got {len(all_posts)}"
    )
