import asyncio
import io
import json
import logging
import os
import re
import socket
import threading
import time
import zipfile
from collections.abc import Callable, Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from httpx import Response

from main import app  # noqa: E402

logger = logging.getLogger(__name__)

TESTDATA_DIR = Path(__file__).parent / "testdata"
TEST_API_KEY = "test-secret-key"

# Test-scoped Temporal configuration.
# NOTE: TEMPORAL_TEST_QUEUE must match the default TASK_QUEUE in task.py because
# task.py reads TEMPORAL_TASK_QUEUE at import time (before this fixture runs),
# so the env var override we set here cannot change it.
TEMPORAL_TEST_HOST = "127.0.0.1"
TEMPORAL_TEST_PORT = 7244
TEMPORAL_TEST_NAMESPACE = "default"
TEMPORAL_TEST_QUEUE = "file-converter"


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.2)
    raise RuntimeError(
        f"Temporal test server did not start on {host}:{port} within {timeout}s: {last_err}"
    )


@pytest.fixture(autouse=True, scope="session")
def temporal_test_env():
    """Start an in-process Temporal dev server + worker for the test session.

    The dev server listens on TEMPORAL_TEST_HOST:TEMPORAL_TEST_PORT and a worker
    polls TEMPORAL_TEST_QUEUE. main.py connects to this server via TEMPORAL_HOST.
    """
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from task import (
        CleanupExpiredZipsWorkflow,
        ProcessFileWorkflow,
        cleanup_expired_zips_activity,
        notify_callback_activity,
        process_file_activity,
    )

    ready = threading.Event()
    startup_error: list[BaseException] = []
    state: dict[str, object] = {}

    def _background() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        state["loop"] = loop

        async def _main() -> None:
            try:
                env = await WorkflowEnvironment.start_local(
                    ip=TEMPORAL_TEST_HOST,
                    port=TEMPORAL_TEST_PORT,
                    namespace=TEMPORAL_TEST_NAMESPACE,
                )
                worker = Worker(
                    env.client,
                    task_queue=TEMPORAL_TEST_QUEUE,
                    max_concurrent_workflow_tasks=25,
                    workflows=[ProcessFileWorkflow, CleanupExpiredZipsWorkflow],
                    activities=[
                        process_file_activity,
                        notify_callback_activity,
                        cleanup_expired_zips_activity,
                    ],
                )
                worker_task = asyncio.create_task(worker.run())
                state["env"] = env
                state["worker"] = worker
                state["worker_task"] = worker_task
                state["stop"] = asyncio.Event()
            except BaseException as exc:
                startup_error.append(exc)
                ready.set()
                return

            ready.set()
            # Keep the loop alive until the fixture is torn down
            try:
                await state["stop"].wait()
            finally:
                try:
                    await worker.shutdown()
                    await worker_task
                finally:
                    await env.shutdown()

        try:
            loop.run_until_complete(_main())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()

    thread = threading.Thread(target=_background, daemon=True)
    thread.start()
    ready.wait(timeout=120)

    if startup_error:
        raise startup_error[0]

    _wait_for_port(TEMPORAL_TEST_HOST, TEMPORAL_TEST_PORT)

    os.environ["TEMPORAL_HOST"] = f"{TEMPORAL_TEST_HOST}:{TEMPORAL_TEST_PORT}"
    os.environ["TEMPORAL_NAMESPACE"] = TEMPORAL_TEST_NAMESPACE
    os.environ["TEMPORAL_TASK_QUEUE"] = TEMPORAL_TEST_QUEUE

    def _signal_stop() -> None:
        loop = state.get("loop")
        stop = state.get("stop")
        if loop and stop and not loop.is_closed():

            async def _set() -> None:
                stop.set()

            asyncio.run_coroutine_threadsafe(_set(), loop)

    yield

    _signal_stop()
    thread.join(timeout=30)
    os.environ.pop("TEMPORAL_HOST", None)
    os.environ.pop("TEMPORAL_NAMESPACE", None)
    os.environ.pop("TEMPORAL_TASK_QUEUE", None)


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """Set the api key in tests."""
    monkeypatch.setenv("F_API_KEY", TEST_API_KEY)


@pytest.fixture(autouse=True)
def ocr_enabled(monkeypatch):
    """Enable OCR for tests that assert OCR output (production default is off)."""
    monkeypatch.setenv("OCR_ENABLED", "true")


@pytest.fixture(autouse=True)
def _reset_temporal_client(monkeypatch):
    """Ensure each test gets a fresh Temporal client bound to its event loop."""
    import main

    monkeypatch.setattr(main, "_temporal_client", None)


@pytest.fixture
def client() -> Generator[TestClient]:
    """Test client for the FastAPI app."""
    with TestClient(app) as cl:
        yield cl


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return auth headers with a valid Bearer token."""
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def testdata_dir() -> Path:
    """Return the path to the testdata directory."""
    return TESTDATA_DIR


@pytest.fixture
def image_file(testdata_dir) -> Path:
    """Return the path to the sample image test file."""
    path = testdata_dir / "images" / "ocr_png.png"
    return path


@pytest.fixture
def debug_zip(request, tmp_path) -> Path:
    """Create a debug zip output directory when DEBUG_ZIP env var is set."""
    if not os.getenv("DEBUG_ZIP"):
        return None
    out = tmp_path / "debug_zips" / request.node.name
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def assert_zip_response(save_debug_zip, debug_zip) -> Callable[[Response, Path | None, str], None]:
    """Return a helper that asserts a response is a valid zip download."""

    def _assert_zip_response(response: Response, zip_filename: str) -> None:
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert zipfile.is_zipfile(io.BytesIO(response.content))

        save_debug_zip(response, debug_zip, zip_filename)

    return _assert_zip_response


@pytest.fixture
def extract_zip_entries() -> Callable[[Response], dict[str, bytes]]:
    """Return a helper that extracts zip entries from a response."""

    def _extract_zip_entries(response: Response) -> dict[str, bytes]:
        buf = io.BytesIO(response.content)
        with zipfile.ZipFile(buf) as z:
            return {name: z.read(name) for name in z.namelist() if not name.endswith("/")}

    return _extract_zip_entries


@pytest.fixture
def save_debug_zip() -> Callable[[Response, Path | None, str], None]:
    """Return a helper that saves response content to a debug directory."""

    def _save_debug_zip(response: Response, debug_dir: Path | None, filename: str) -> None:
        if debug_dir is None:
            return
        dest = debug_dir / filename
        dest.write_bytes(response.content)
        logger.info(f"DEBUG_ZIP: saved to {dest}")

    return _save_debug_zip


@pytest.fixture
def assert_metadata_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts metadata file content matches expected."""

    def _assert_metadata_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = json.loads(entries[actual_path].decode("utf-8"))
        assert actual == expected_content, f"Metadata content mismatch for {actual_path}.\n"

    return _assert_metadata_content


@pytest.fixture
def assert_markdownfile_content() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts markdown file content matches expected."""

    def _assert_markdownfile_content(
        actual_path: str, expected_content: str, entries: dict[str, bytes]
    ) -> None:
        actual = entries[actual_path].decode("utf-8")
        actual = re.sub(r"/tmp/tmp[^/]+/", "/tmp/tmpXXXXXX/", actual)

        assert actual == expected_content, f"Markdown content mismatch for {actual_path}.\n"
        assert actual == expected_content

    return _assert_markdownfile_content


@pytest.fixture
def assert_markdown() -> Callable[[str, str, dict[str, bytes]], None]:
    """Return a helper that asserts markdown file content and header matches expected."""

    def extract_header_and_content(text):
        match = re.search(r"---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
        if not match:
            return None, text  # no header → whole text is content

        header_text = match.group(1)
        content = match.group(2)

        data = yaml.safe_load(header_text)

        return data, content

    def _assert_markdown(
        actual_path: str,
        expected_content: str,
        expected_header: dict,
        entries: dict[str, bytes],
    ) -> None:
        actual = entries[actual_path].decode("utf-8")
        header, content = extract_header_and_content(actual)
        if "keywords" in expected_header and (val := expected_header.pop("keywords")):
            assert sorted(val) == sorted(header.pop("keywords"))
        assert header == expected_header
        assert content == expected_content, f"Markdown content mismatch for {actual_path}.\n"
        assert content == expected_content

    return _assert_markdown


@pytest.fixture
def convert_and_wait(
    client, auth_headers
) -> Callable[[bytes, str, str | None, str | None], tuple[Response, dict]]:
    """POST /convert and poll /jobs/{job_id} until the workflow reaches a
    terminal state.

    Returns the (convert_response, job_detail) pair. The caller can then
    inspect the convert response (status_code, JSON body) and the final
    /jobs/{job_id} payload.
    """

    def _convert_and_wait(
        content: bytes,
        filename: str,
        content_type: str = "text/plain",
        callback_url: str | None = None,
        timeout: float = 120.0,
    ) -> tuple[Response, dict]:
        files = {"file": (filename, content, content_type)}
        data = {}
        if callback_url is not None:
            data["callback_url"] = callback_url
        resp = client.post("/convert", files=files, data=data, headers=auth_headers)
        assert resp.status_code in (200, 202), resp.content
        job_id = resp.json()["job_id"]

        deadline = time.time() + timeout
        last_detail: dict = {}
        while time.time() < deadline:
            detail_resp = client.get(f"/jobs/{job_id}", headers=auth_headers)
            assert detail_resp.status_code == 200, detail_resp.content
            last_detail = detail_resp.json()
            status_val = last_detail.get("status_detail", {}).get("status") or last_detail.get(
                "status"
            )
            if status_val in ("completed", "failed"):
                return resp, last_detail
            time.sleep(0.5)
        raise AssertionError(
            f"Job {job_id} did not finish within {timeout}s. Last detail: {last_detail}"
        )

    return _convert_and_wait


@pytest.fixture
def callback_receiver():
    """Run a tiny threaded HTTP server that captures POST bodies.

    Yields an object with:
      - .url: the URL to give to /convert as callback_url
      - .posts: list of (json_body, headers) tuples received so far
      - .set_status(code): respond with `code` until changed
      - .wait_for(count, timeout): block until `count` posts have arrived
      - .stop(): shut the server down (called automatically on teardown)
    """

    class _State:
        def __init__(self) -> None:
            self.posts: list[tuple[dict, dict]] = []
            self._cond = threading.Condition()
            self.status_code: int = 200
            self.server: ThreadingHTTPServer | None = None
            self.port: int = 0

        @property
        def url(self) -> str:
            return f"http://127.0.0.1:{self.port}/hook"

        def set_status(self, code: int) -> None:
            self.status_code = code

        def wait_for(self, count: int, timeout: float = 30.0) -> list[tuple[dict, dict]]:
            deadline = time.time() + timeout
            with self._cond:
                while len(self.posts) < count and time.time() < deadline:
                    if not self._cond.wait(timeout=1.0):
                        break
                return list(self.posts)

    state = _State()

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except Exception:
                body = {"raw": raw.decode("utf-8", errors="replace")}
            with state._cond:
                state.posts.append((body, dict(self.headers)))
                state._cond.notify_all()
            self.send_response(state.status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args, **kwargs) -> None:  # silence stderr noise
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    state.server = server
    state.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
