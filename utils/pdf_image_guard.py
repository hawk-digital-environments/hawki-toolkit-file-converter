"""Guard against oversized raster images in untrusted uploads.

A small PDF can embed a huge scanned raster (the production incident: an
8.5 MB single-page city plan carrying a ~96-megapixel JPEG). Every stage of
the xberg pipeline -- image decode, OCR, webp re-encode -- allocates buffers
proportional to the pixel count, so a single such image multiplies into the
observed >1.2 GB peak RSS and seven-minute conversions, and repeated uploads
can exhaust host memory.

The real improvement is to avoid decoding the full-resolution raster in the first place,
but thats only possible in xberg's codebase.
In the meantime the idea is to guard against input with large rasters by downscaling
them to a reasonable cap before they enter the pipeline.

So the guard rewrites oversized images *before* xberg sees the file:

- Detection is free: ``/Width`` and ``/Height`` are plain integers in the PDF
  object dictionary, so no pixel is decoded to decide whether a PDF needs
  treatment.
- JPEG streams (``/DCTDecode`` -- what scanners emit) are downsampled with
  Pillow's ``draft()`` DCT-scaled decoding: the JPEG is decoded directly at
  1/2, 1/4 or 1/8 resolution, so the full-resolution raster is never held in
  memory.
- The replacement keeps the image an XObject at the same position: PDF
  content streams draw images into a fixed rectangle on the page, so a
  smaller raster simply renders at a lower effective DPI. Page geometry,
  text and vectors are untouched.
- Downscaling can land in a mid-size range (~4000-4900 px) where OCR is
  pathologically slow (~190 s vs ~3 s outside it). Results that are still
  huge (>= 20 megapixels) are therefore upscaled back to the cap with
  BICUBIC. The root cause is not clear but the effect is measured and repeatable, 
  so the escape rule is applied. This needs more insights from OCR and xberg codebases.

Images below the threshold are left byte-identical (the original ``bytes``
object is returned). Non-JPEG filters that Pillow cannot decode cheaply
(JBIG2, JPX, ...) are skipped with a warning -- conversion then proceeds as
before, bounded only by the pre-existing pipeline behavior.

Standalone uploaded images get the same treatment via
:func:`downscale_image_bytes` before they enter xberg.
"""

import io
import logging
import os

import pikepdf
from PIL import Image, ImageOps

logger = logging.getLogger("converter")

DEFAULT_MAX_IMAGE_MEGAPIXELS = 25.0
DEFAULT_MAX_IMAGE_DIMENSION = 6000

# This module exists precisely to process untrusted oversized rasters with
# bounded memory; Pillow's decompression-bomb guard would only spam warnings.
Image.MAX_IMAGE_PIXELS = None

# libjpeg supports these draft (DCT scaling) denominators.
_DRAFT_STEPS = (1, 2, 4, 8)

# Giant sparse rasters (e.g. scanned city plans) hit a pathological
# tesseract/xberg path below roughly 5000 px: measured 126-245 s extraction
# at 4000-4900 px vs 3-5 s at >= 6000 px -- with the same information
# content, since a BICUBIC upscale of the 4900 px draft ran 3.1 s. Rasters
# that are still giant (>= 20 MP) after downscaling are therefore upscaled
# to the cap; ordinary documents (e.g. a 600-DPI A4 scan that drafts to its
# 300-DPI equivalent, ~8.7 MP) stay untouched.
#
# NOTE: landing on the cap is NOT universally fast -- a 13000 px synthetic
# sheet measured slow and textless at every tested size >= 3250 px (198 s
# at 6000 px, 292 s at 6500 px) while its 3250 px draft was fast (14 s).
# The escape rule below is the best measured compromise: fast in all
# tested cases, with text where any size yields it.
_UPSCALE_MIN_PIXELS = 20_000_000


def _escape_slow_band(im: Image.Image, cap: int) -> Image.Image:
    """Upscale a still-giant raster to the cap to dodge the slow OCR band."""
    if im.width * im.height >= _UPSCALE_MIN_PIXELS and max(im.width, im.height) < cap:
        scale = cap / max(im.width, im.height)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.BICUBIC)
    return im


def _max_megapixels() -> float:
    return float(os.getenv("PDF_MAX_IMAGE_MEGAPIXELS", str(DEFAULT_MAX_IMAGE_MEGAPIXELS)))


def _max_dimension() -> int:
    return int(os.getenv("PDF_IMAGE_MAX_DIMENSION", str(DEFAULT_MAX_IMAGE_DIMENSION)))


def _decode_jpeg_downscaled(data: bytes, max_dimension: int) -> Image.Image:
    """Decode JPEG bytes to at most ``max_dimension`` on the longest side.

    Uses DCT-scaled decoding (``draft``) so the full-resolution raster is
    never materialized: the largest power-of-two scale whose result still
    fits the cap is requested directly. If even a 1/8 decode exceeds the cap
    (giant images), the 1/8 decode is resized down afterwards -- one
    bounded-size copy instead of a full-size one.
    """
    im = Image.open(io.BytesIO(data))
    step = next(
        (s for s in _DRAFT_STEPS if max(im.width // s, im.height // s) <= max_dimension),
        _DRAFT_STEPS[-1],
    )
    if step > 1:
        im.draft(_draft_mode(im.mode), (im.width // step, im.height // step))
    im.load()
    if max(im.width, im.height) > max_dimension:
        im.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    return im


def _draft_mode(mode: str) -> str:
    """Mode hint for ``draft``; CMYK JPEGs decode as CMYK regardless."""
    return "L" if mode == "L" else "RGB"


def _to_persistable(im: Image.Image) -> Image.Image:
    """Normalize a decoded image for re-embedding as JPEG."""
    if im.mode == "CMYK":
        # Adobe-convention CMYK JPEGs decode inverted; Pillow keeps them that
        # way, so negate before converting or colors come out swapped.
        im = ImageOps.invert(im)
    if im.mode not in ("L", "RGB"):
        im = im.convert("RGB")
    return im


def _encode_jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _image_filters(obj: pikepdf.Stream) -> list[str]:
    filt = obj.get(pikepdf.Name.Filter)
    if filt is None:
        return []
    if isinstance(filt, pikepdf.Array):
        return [str(f) for f in filt]
    return [str(filt)]


def _replace_image_stream(
    obj: pikepdf.Stream, jpeg: bytes, width: int, height: int, gray: bool
) -> None:
    """Overwrite an image XObject in place with pre-encoded JPEG bytes.

    ``Stream.write`` stores the bytes verbatim when handed a filter qpdf has
    no encoder for (DCTDecode), so the JPEG we encoded is what lands in the
    file. Stale dictionary entries from the old encoding are removed.
    """
    obj.write(jpeg, filter=pikepdf.Name("/DCTDecode"))
    obj.Width = width
    obj.Height = height
    obj.BitsPerComponent = 8
    obj.ColorSpace = pikepdf.Name.DeviceGray if gray else pikepdf.Name.DeviceRGB
    for stale in (pikepdf.Name.DecodeParms, pikepdf.Name.Decode):
        if stale in obj:
            del obj[stale]


def _downscale_dct(obj: pikepdf.Stream, max_dimension: int) -> bool:
    """Downscale a DCTDecode image XObject in place. True if replaced."""
    im = _decode_jpeg_downscaled(bytes(obj.read_raw_bytes()), max_dimension)
    im = _escape_slow_band(im, max_dimension)
    im = _to_persistable(im)
    _replace_image_stream(obj, _encode_jpeg(im), im.width, im.height, im.mode == "L")
    return True


def _downscale_flate(obj: pikepdf.Stream, max_dimension: int) -> bool:
    """Downscale an uncompressed-capable image XObject in place.

    Only the common scanned-document cases are handled: 8-bit DeviceGray or
    DeviceRGB with FlateDecode. Anything else returns False and is skipped
    with a warning by the caller.
    """
    colorspace = str(obj.get(pikepdf.Name.ColorSpace, ""))
    mode = {"/DeviceGray": "L", "/DeviceRGB": "RGB"}.get(colorspace)
    if mode is None or int(obj.get(pikepdf.Name.BitsPerComponent, 0)) != 8:
        return False
    width, height = int(obj.Width), int(obj.Height)
    data = bytes(obj.read_bytes())
    if len(data) != width * height * (1 if mode == "L" else 3):
        return False
    im = Image.frombytes(mode, (width, height), data)
    im.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    im = _to_persistable(_escape_slow_band(im, max_dimension))
    _replace_image_stream(obj, _encode_jpeg(im), im.width, im.height, im.mode == "L")
    return True


def shrink_oversized_pdf_images(
    data: bytes,
    *,
    max_megapixels: float | None = None,
    max_dimension: int | None = None,
) -> bytes:
    """Return PDF bytes with oversized embedded images downscaled.

    An image is oversized when its pixel count exceeds ``max_megapixels``
    (env ``PDF_MAX_IMAGE_MEGAPIXELS``, default 25) AND its longest side
    exceeds ``max_dimension`` (env ``PDF_IMAGE_MAX_DIMENSION``, default
    6000); such images are downscaled so their longest side is at most
    ``max_dimension`` (still-giant rasters that would land in tesseract's
    slow band below the cap are upscaled to it -- see
    ``_UPSCALE_MIN_PIXELS``). PDFs without oversized images come back as
    the exact ``bytes`` object passed in.

    Never raises: on any parse or processing error the original bytes are
    returned and a warning logged, so conversion proceeds as before.
    """
    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            changed = False
            for obj in pdf.objects:
                if not isinstance(obj, pikepdf.Stream):
                    continue
                if obj.get(pikepdf.Name.Subtype) != pikepdf.Name.Image:
                    continue
                if obj.get(pikepdf.Name.ImageMask, False):
                    continue  # 1-bpp stencils, never large
                width, height = int(obj.Width), int(obj.Height)
                cap = max_dimension if max_dimension is not None else _max_dimension()
                if (
                    width * height
                    <= (max_megapixels if max_megapixels is not None else _max_megapixels()) * 1e6
                    or max(width, height) <= cap
                ):
                    continue
                filters = _image_filters(obj)
                try:
                    if filters == ["/DCTDecode"]:
                        replaced = _downscale_dct(obj, cap)
                    elif "/DCTDecode" not in filters:
                        # FlateDecode or unfiltered raw samples; the helper
                        # validates colorspace/bpp and declines if unsupported.
                        replaced = _downscale_flate(obj, cap)
                    else:
                        replaced = False
                except Exception:
                    logger.warning(
                        "pdf image guard: failed to downscale %dx%d image (%s); leaving it unchanged",
                        width,
                        height,
                        "/".join(filters) or "unfiltered",
                        exc_info=True,
                    )
                    continue
                if replaced:
                    logger.info(
                        "pdf image guard: downscaled %dx%d image to %dx%d (cap %d)",
                        width,
                        height,
                        int(obj.Width),
                        int(obj.Height),
                        cap,
                    )
                    changed = True
                else:
                    logger.warning(
                        "pdf image guard: %dx%d image exceeds the megapixel cap but its filter"
                        " (%s) is not supported for cheap downscaling; leaving it unchanged",
                        width,
                        height,
                        "/".join(filters) or "unfiltered",
                    )
            if not changed:
                return data
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()
    except Exception:
        logger.warning(
            "pdf image guard: could not process PDF; passing it through unchanged", exc_info=True
        )
        return data


def downscale_image_bytes(data: bytes, max_dimension: int | None = None) -> bytes:
    """Downscale a standalone image so its longest side fits ``max_dimension``.

    Same contract as :func:`shrink_oversized_pdf_images`: the original
    ``bytes`` object is returned when nothing needs to change, and any error
    falls back to the original bytes. JPEG inputs use DCT-scaled decoding;
    other formats decode once (bounded by a single raster copy). Animated
    images are passed through untouched, and EXIF orientation is applied
    before resizing so the stored result renders upright.
    """
    cap = max_dimension if max_dimension is not None else _max_dimension()
    try:
        with Image.open(io.BytesIO(data)) as im:
            if getattr(im, "n_frames", 1) > 1:
                return data
            needs = max(im.width, im.height) > cap
            if not needs:
                return data
            src_format = im.format
            if src_format == "JPEG":
                # Transpose after the (draft) decode -- orientation applies to
                # the whole image, so transposing the smaller raster is
                # equivalent and keeps EXIF-oriented photos upright.
                out_im = _decode_jpeg_downscaled(data, cap)
                out_im = ImageOps.exif_transpose(out_im)
            else:
                im.load()
                out_im = ImageOps.exif_transpose(im)
                out_im.thumbnail((cap, cap), Image.LANCZOS)
            out_im = _escape_slow_band(out_im, cap)
            out_im = _to_persistable(out_im)
        buf = io.BytesIO()
        try:
            out_im.save(buf, src_format, quality=85) if src_format != "PNG" else out_im.save(
                buf, "PNG"
            )
        except (ValueError, OSError):
            # Format without a save path for this mode; fall back to PNG.
            buf = io.BytesIO()
            out_im.save(buf, "PNG")
        logger.info(
            "image guard: downscaled uploaded image to %dx%d (cap %d)",
            out_im.width,
            out_im.height,
            cap,
        )
        return buf.getvalue()
    except Exception:
        logger.warning(
            "image guard: could not downscale image; passing it through unchanged", exc_info=True
        )
        return data
