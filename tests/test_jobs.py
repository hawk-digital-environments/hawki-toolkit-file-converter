def test_jobs_list_returns_array_with_raw_temporal_fields(
    convert_and_wait, client, auth_headers
) -> None:
    """GET /jobs returns a list of jobs with raw Temporal passthrough fields."""
    convert_and_wait(b"jobs list payload", "jobslist.txt")

    resp = client.get("/jobs", headers=auth_headers)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "jobs" in body
    assert body["count"] == len(body["jobs"])
    assert body["count"] >= 1

    sample = body["jobs"][0]
    # Required raw passthrough keys
    for key in (
        "job_id",
        "run_id",
        "workflow_type",
        "task_queue",
        "status",
        "start_time",
        "history_length",
        "search_attributes",
    ):
        assert key in sample, f"missing key {key} in {sample}"


def test_jobs_list_status_filter(convert_and_wait, client, auth_headers) -> None:
    """?status= filter narrows the result set."""
    convert_and_wait(b"filter target", "filter.txt")

    completed = client.get("/jobs?status=COMPLETED", headers=auth_headers)
    assert completed.status_code == 200
    completed_body = completed.json()
    assert completed_body["count"] >= 1
    statuses = sorted({j["status"] for j in completed_body["jobs"]})
    assert statuses == ["COMPLETED"], (
        f"filter should narrow to COMPLETED, got statuses={statuses}; "
        f"sample={completed_body['jobs'][:2]}"
    )

    running = client.get("/jobs?status=RUNNING", headers=auth_headers)
    assert running.status_code == 200
    assert all(j["status"] == "RUNNING" for j in running.json()["jobs"])


def test_jobs_list_invalid_status_filter_returns_422(client, auth_headers) -> None:
    """An unknown status value returns 422 (FastAPI enum validation)."""
    resp = client.get("/jobs?status=BOGUS", headers=auth_headers)
    assert resp.status_code == 422


def test_jobs_detail_returns_merged_temporal_and_query(
    convert_and_wait, client, auth_headers
) -> None:
    """GET /jobs/{job_id} merges Temporal describe with our status query."""
    convert_resp, _ = convert_and_wait(b"detail payload", "detail.txt")
    job_id = convert_resp.json()["job_id"]

    resp = client.get(f"/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.content
    body = resp.json()

    # Temporal fields
    assert body["job_id"] == job_id
    assert body["workflow_type"] == "ProcessFileWorkflow"
    # Our custom status query result
    assert "status_detail" in body
    assert body["status_detail"]["status"] == "completed"


def test_jobs_detail_unknown_job_returns_404(client, auth_headers) -> None:
    """GET /jobs/{unknown_id} returns 404."""
    resp = client.get("/jobs/convert-does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "job_not_found"


def test_jobs_missing_auth_returns_401(client) -> None:
    resp = client.get("/jobs")
    assert resp.status_code == 401
