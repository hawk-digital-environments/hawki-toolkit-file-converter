def test_cleanup_schedule_registered_on_startup(client, auth_headers) -> None:
    """The lifespan startup registers the cleanup schedule in Temporal."""
    import asyncio

    from main import CLEANUP_SCHEDULE_ID, get_temporal_client

    async def _check() -> bool:
        cl = await get_temporal_client()
        handle = cl.get_schedule_handle(CLEANUP_SCHEDULE_ID)
        desc = await handle.describe()
        # state.paused is False when the schedule is active
        return desc.schedule.state.paused is False

    assert asyncio.run(_check()) is True


def test_cleanup_workflow_deletes_old_zips(
    convert_and_wait, monkeypatch, client, auth_headers
) -> None:
    """Running CleanupExpiredZipsWorkflow removes expired job directories."""
    import asyncio
    import os
    import time

    from main import get_temporal_client, job_zip_path
    from task import SHARED_TMP, TASK_QUEUE, CleanupExpiredZipsWorkflow

    convert_resp, _ = convert_and_wait(b"cleanup target", "cln.txt")
    job_id = convert_resp.json()["job_id"]
    zip_path = job_zip_path(job_id)
    assert zip_path.exists()

    # Backdate the zip so it's clearly past a 1-hour TTL.
    old_ts = time.time() - 2 * 3600
    os.utime(zip_path, (old_ts, old_ts))

    async def _run_cleanup() -> list[str]:
        cl = await get_temporal_client()
        return await cl.execute_workflow(
            CleanupExpiredZipsWorkflow.run,
            args=[str(SHARED_TMP), 1.0],  # TTL = 1 hour
            id=f"cleanup-direct-{job_id}",
            task_queue=TASK_QUEUE,
        )

    removed = asyncio.run(_run_cleanup())
    assert job_id in removed
    assert not zip_path.exists()
