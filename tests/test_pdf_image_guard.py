"""Unit tests for the oversized-image guard (utils/pdf_image_guard.py).

The PDFs are built with Pillow, whose PDF writer embeds RGB images as
DCTDecode (JPEG) streams -- the same filter real scanners produce, so the
draft-decode fast path is the one exercised here.
"""

import io

import pikepdf
import pytest
from PIL import Image

from utils.pdf_image_guard import (
    DEFAULT_MAX_IMAGE_MEGAPIXELS,
    downscale_image_bytes,
    shrink_oversized_pdf_images,
)


def _make_pdf_bytes(width: int, height: int, resolution: int = 200) -> bytes:
    """A single-page PDF embedding one RGB JPEG of the given size."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 160)).save(buf, "PDF", resolution=resolution)
    return buf.getvalue()


def _make_flate_pdf_bytes(width: int, height: int) -> bytes:
    """A single-page PDF embedding one uncompressed DeviceRGB image."""
    import pikepdf

    pdf = pikepdf.new()
    # make_stream stores raw samples; qpdf Flate-compresses them on save.
    image = pdf.make_stream(bytes(width * height * 3))
    image.Type = pikepdf.Name.XObject
    image.Subtype = pikepdf.Name.Image
    image.Width = width
    image.Height = height
    image.ColorSpace = pikepdf.Name.DeviceRGB
    image.BitsPerComponent = 8
    page = pdf.add_blank_page(page_size=(width, height))
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=pdf.make_indirect(image)))
    page.Contents = pdf.make_stream(f"q {width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ".encode())
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _pdf_images(data: bytes) -> list[tuple[int, int, str]]:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        out = []
        for obj in pdf.objects:
            if (
                isinstance(obj, pikepdf.Stream)
                and obj.get(pikepdf.Name.Subtype) == pikepdf.Name.Image
            ):
                filters = obj.get(pikepdf.Name.Filter)
                filt = (
                    str(filters)
                    if not isinstance(filters, pikepdf.Array)
                    else "/".join(map(str, filters))
                )
                out.append((int(obj.Width), int(obj.Height), filt))
        return out


def test_pdf_below_threshold_is_returned_unchanged() -> None:
    """A small PDF must come back as the exact same bytes object."""
    data = _make_pdf_bytes(2000, 1400)  # 2.8 MP, below any default threshold
    result = shrink_oversized_pdf_images(data, max_megapixels=10, max_dimension=1000)
    assert result is data


def test_pdf_with_oversized_jpeg_is_downscaled() -> None:
    """An embedded JPEG above the megapixel threshold is rewritten smaller."""
    data = _make_pdf_bytes(6000, 4000)  # 24 MP
    assert _pdf_images(data) == [(6000, 4000, "/DCTDecode")]

    result = shrink_oversized_pdf_images(data, max_megapixels=10, max_dimension=2000)
    assert result is not data
    assert result != data

    (width, height, filt) = _pdf_images(result)[0]
    assert filt == "/DCTDecode"
    assert max(width, height) <= 2000
    # Roughly preserved aspect ratio.
    assert abs((width / height) - 1.5) < 0.15


def test_giant_sheet_is_upscaled_above_slow_band() -> None:
    """9800 px with a 6000 cap drafts at 1/2 (4900 px) -- that lands in the
    measured slow tesseract band, so the guard upscales to the full cap."""
    data = _make_pdf_bytes(9800, 9778)  # ~96 MP, the incident's city plan
    result = shrink_oversized_pdf_images(data, max_megapixels=25, max_dimension=6000)
    (width, height, filt) = _pdf_images(result)[0]
    assert filt == "/DCTDecode"
    assert width == 6000
    assert abs(height - 5987) <= 1  # 4889 upscaled by 6000/4900


def test_a4_600dpi_scan_is_not_upscaled() -> None:
    """A 600-DPI A4 scan drafts to its 300-DPI equivalent (~8.7 MP).

    Ordinary documents stay untouched by the slow-band escape; only
    still-giant rasters (>= 20 MP) are upscaled.
    """
    data = _make_pdf_bytes(4960, 7016)  # 34.8 MP
    result = shrink_oversized_pdf_images(data, max_megapixels=25, max_dimension=6000)
    (width, height, _) = _pdf_images(result)[0]
    assert (width, height) == (2480, 3508)


def test_flate_image_is_rewritten_as_jpeg() -> None:
    """FlateDecode rasters are decoded once, downscaled to fit the cap and
    re-embedded as JPEG."""
    data = _make_flate_pdf_bytes(8000, 1000)  # 8 MP uncompressed RGB
    assert _pdf_images(data) == [(8000, 1000, "/FlateDecode")]
    result = shrink_oversized_pdf_images(data, max_megapixels=1, max_dimension=2000)
    (width, height, filt) = _pdf_images(result)[0]
    assert filt == "/DCTDecode"  # re-encoded as JPEG
    assert (width, height) == (2000, 250)  # 8000/1000 scaled by 1/4


def test_over_mp_budget_but_within_cap_is_unchanged() -> None:
    """Pixels over the megapixel budget but longest side within the cap
    need no rewrite and pass through byte-identical."""
    data = _make_pdf_bytes(6000, 5000)  # 30 MP, longest side == cap
    assert shrink_oversized_pdf_images(data, max_megapixels=25, max_dimension=6000) is data


def test_downscaled_pdf_still_opens_and_keeps_page_geometry() -> None:
    """The rewritten PDF keeps its page count and MediaBox (placement)."""
    data = _make_pdf_bytes(6000, 4000)
    result = shrink_oversized_pdf_images(data, max_megapixels=10, max_dimension=2000)

    with pikepdf.open(io.BytesIO(result)) as original, pikepdf.open(io.BytesIO(data)) as downscaled:
        assert len(downscaled.pages) == len(original.pages) == 1
        assert downscaled.pages[0].MediaBox == original.pages[0].MediaBox


def test_corrupt_pdf_passes_through_unchanged() -> None:
    """Garbage bytes must never raise; the original object comes back."""
    data = b"%PDF-1.7 this is not a real pdf"
    assert shrink_oversized_pdf_images(data, max_megapixels=1, max_dimension=100) is data


def test_threshold_boundary_is_inclusive() -> None:
    """width * height == threshold megapixels counts as not oversized."""
    width, height = 5000, 2000  # exactly 10 MP
    data = _make_pdf_bytes(width, height)
    result = shrink_oversized_pdf_images(data, max_megapixels=10, max_dimension=1000)
    assert result is data


def test_default_threshold_catches_city_plan() -> None:
    """Defaults catch the incident's ~96 MP image without explicit args."""
    data = _make_pdf_bytes(9800, 9778)
    result = shrink_oversized_pdf_images(data)
    (width, height, _) = _pdf_images(result)[0]
    assert width == 6000  # upscaled above the slow band
    assert max(width, height) <= 6000


def test_image_bytes_giant_jpeg_upscaled_above_slow_band() -> None:
    """Standalone giant uploads get the same slow-band escape as PDFs."""
    buf = io.BytesIO()
    Image.new("RGB", (9800, 9778), (10, 200, 30)).save(buf, "JPEG", quality=70)
    result = downscale_image_bytes(buf.getvalue(), max_dimension=6000)
    with Image.open(io.BytesIO(result)) as im:
        assert im.format == "JPEG"
        assert im.width == 6000


def test_image_bytes_jpeg_downscaled() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (9000, 6000), (10, 200, 30)).save(buf, "JPEG", quality=70)
    result = downscale_image_bytes(buf.getvalue(), max_dimension=6000)
    with Image.open(io.BytesIO(result)) as im:
        assert im.format == "JPEG"
        assert max(im.width, im.height) <= 6000


def test_image_bytes_png_downscaled() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (8000, 1000), (10, 200, 30)).save(buf, "PNG")
    result = downscale_image_bytes(buf.getvalue(), max_dimension=2000)
    with Image.open(io.BytesIO(result)) as im:
        assert im.format == "PNG"
        assert im.width <= 2000


def test_image_bytes_small_is_unchanged() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (500, 400), (0, 0, 0)).save(buf, "JPEG")
    assert downscale_image_bytes(buf.getvalue(), max_dimension=6000) is buf.getvalue()


def test_image_bytes_grayscale_stays_grayscale() -> None:
    """Grayscale JPEGs re-embed as DeviceGray, not tripled to RGB."""
    buf = io.BytesIO()
    Image.new("L", (7000, 5000), 128).save(buf, "JPEG", quality=70)
    result = downscale_image_bytes(buf.getvalue(), max_dimension=3000)
    with Image.open(io.BytesIO(result)) as im:
        assert im.mode == "L"
        assert max(im.width, im.height) <= 3000


def test_image_bytes_corrupt_falls_back_to_original() -> None:
    data = b"\xff\xd8\xff\xe0 truncated jpeg"
    assert downscale_image_bytes(data, max_dimension=100) is data


def test_process_file_core_applies_guard_to_pdfs_only(monkeypatch) -> None:
    """Only .pdf uploads are rewritten; other extensions flow through."""
    from utils import processor

    pdf_bytes = _make_pdf_bytes(9800, 9778)
    docx_bytes = b"PK\x03\x04 not really a docx but non-pdf"

    seen: list[tuple[str, bytes]] = []

    def fake_shrink(data: bytes, **_: object) -> bytes:
        seen.append(("guard", data))
        return data

    async def fake_process(file_path, zip_dir, assets_dir):  # noqa: ANN001
        seen.append(("document", file_path.read_bytes()))

    async def fake_process_image(file_path, assets_dir):  # noqa: ANN001
        seen.append(("image", file_path.read_bytes()))

    monkeypatch.setattr(processor, "shrink_oversized_pdf_images", fake_shrink)
    monkeypatch.setattr(processor, "process_file_contents", fake_process)
    monkeypatch.setattr(processor, "process_image_content", fake_process_image)

    import asyncio

    asyncio.run(processor.process_file_core(docx_bytes, "notes.docx"))
    asyncio.run(processor.process_file_core(pdf_bytes, "plan.pdf"))

    calls = dict(reversed(seen))  # last call per kind
    assert calls["document"] == docx_bytes  # non-PDF bytes written unmodified
    assert calls["guard"] is pdf_bytes  # guard invoked with the PDF bytes object
    assert [kind for kind, _ in seen if kind == "guard"] == ["guard"]  # PDFs only


def test_default_max_megapixels_matches_docs() -> None:
    assert DEFAULT_MAX_IMAGE_MEGAPIXELS == 25.0


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
