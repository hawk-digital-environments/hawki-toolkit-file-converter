"""Profiling test for the PDF conversion pipeline.

Run with:
    uv run pytest tests/test_profile_pdf.py -m profile -s

Outputs (under ./profiles/):
    profile_pdf_ocr_on.html        pyinstrument call-tree (open in a browser)
    profile_pdf_ocr_off.html       same, with OCR disabled
    profile_pdf_ocr_on.pyisession  re-openable pyinstrument session

Also prints a per-phase wall-clock breakdown and the pyinstrument text tree to the
pytest log so hotspots are visible immediately.

This calls ``process_file_core()`` directly in-process rather than going through
the ``/extract`` HTTP + Temporal path. The Temporal worker runs on a separate
background thread with its own event loop (tests/conftest.py), so a profiler
attached to the test thread would not capture its work; calling the engine
directly yields accurate hotspot attribution.
"""

import inspect
import io
import time
import zipfile
from pathlib import Path

import pytest

from utils import processor

PROFILE_OUT_DIR = Path(__file__).parent.parent / "profiles"


@pytest.fixture
def profile_pdf_file(testdata_dir) -> Path:
    """Path to the PDF used for profiling (lives in tests/testdata)."""
    return testdata_dir / "dl.pdf"


# --- per-phase wall-clock accounting -----------------------------------------

# phase_name -> total seconds spent inside that function across the run.
_phase_times: dict[str, float] = {}


def _wrap(label: str, fn: object) -> object:
    """Wrap a sync/async/async-gen function, recording its wall-clock time."""

    if inspect.isasyncgenfunction(fn):

        async def gen_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                async for item in fn(*args, **kwargs):
                    yield item
            finally:
                _phase_times[label] = _phase_times.get(label, 0.0) + (time.perf_counter() - start)

        return gen_wrapper

    if inspect.iscoroutinefunction(fn):

        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                _phase_times[label] = _phase_times.get(label, 0.0) + (time.perf_counter() - start)

        return async_wrapper

    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            _phase_times[label] = _phase_times.get(label, 0.0) + (time.perf_counter() - start)

    return sync_wrapper


def _install_phase_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the pipeline's phase functions with timing wrappers.

    These are module-global lookups inside ``process_file_contents`` /
    ``process_file_core``, so patching ``utils.processor.<name>`` is picked up
    by the live call path. No production code is modified.
    """
    _phase_times.clear()
    for name in (
        "extract",
        "_save_extracted_images",
        "finalize_chunk",
        "_write_metadata",
    ):
        monkeypatch.setattr(processor, name, _wrap(name, getattr(processor, name)))


def _print_phase_report(total_wall: float) -> None:
    print("\n=== Per-phase wall-clock breakdown ===")
    print("(times are cumulative; nested phases do not sum to 100%)\n")
    rows = sorted(_phase_times.items(), key=lambda kv: kv[1], reverse=True)
    for name, secs in rows:
        pct = (secs / total_wall * 100.0) if total_wall else 0.0
        print(f"  {name:<22} {secs * 1000:>9.2f} ms  ({pct:5.1f}%)")
    print(f"  {'(total profiled run)':<22} {total_wall * 1000:>9.2f} ms")


# --- the profiling test ------------------------------------------------------


@pytest.fixture
def ocr_on():
    """Control knob to enable/disable ocr."""
    return True


@pytest.mark.profile
@pytest.mark.asyncio
async def test_profile_pdf_pipeline(
    profile_pdf_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    ocr_on: bool,
) -> None:
    """Profile ``process_file_core`` for a PDF and report hotspots."""
    pytest.importorskip("pyinstrument")
    from pyinstrument import Profiler
    from pyinstrument.renderers import SessionRenderer

    monkeypatch.setenv("OCR_ENABLED", "true" if ocr_on else "false")

    pdf_bytes = profile_pdf_file.read_bytes()
    print(
        f"\nProfiling {profile_pdf_file.name} "
        f"({len(pdf_bytes)} bytes), OCR_ENABLED={'true' if ocr_on else 'false'}"
    )

    # Warm up so one-shot lazy loading (xberg/PaddleOCR init) doesn't skew
    # the timed run. The result is discarded.
    await processor.process_file_core(pdf_bytes, "warmup.pdf")

    _install_phase_timers(monkeypatch)

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    start = time.perf_counter()
    zip_bytes, _headers = await processor.process_file_core(pdf_bytes, "profile.pdf")
    total_wall = time.perf_counter() - start
    profiler.stop()

    # Sanity: the run must still produce a valid zip.
    assert zip_bytes, "process_file_core returned empty zip bytes"
    assert zipfile.is_zipfile(io.BytesIO(zip_bytes)), "profiled run did not produce a valid zip"

    _print_phase_report(total_wall)

    # pyinstrument text tree -> log.
    print("\n=== pyinstrument call tree ===")
    print(profiler.output_text(show_all=False, color=False))

    # Artifacts for offline browsing.
    label = "ocr_on" if ocr_on else "ocr_off"
    PROFILE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = PROFILE_OUT_DIR / f"profile_pdf_{label}.html"
    profiler.write_html(str(html_path))
    session_path = PROFILE_OUT_DIR / f"profile_pdf_{label}.pyisession"
    session_path.write_text(SessionRenderer().render(profiler.last_session), encoding="utf-8")
    print(f"\nWrote {html_path}")
    print(f"Wrote {session_path}  (reopen with: pyinstrument {session_path})")
