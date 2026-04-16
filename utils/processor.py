"""
Unified file-to-Markdown processor using kreuzberg.

Supports 91+ file formats including PDF, Word, Excel, PowerPoint,
images, HTML, emails, archives, and more.
"""

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from kreuzberg import (
    ExtractionConfig,
    HierarchyConfig,
    ImageExtractionConfig,
    OcrConfig,
    PageConfig,
    PdfConfig,
    extract_file,
)
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from utils.helper import make_content_disposition

# For kreuzberg configuration interface and defaults see: 
# https://github.com/kreuzberg-dev/kreuzberg/blob/v4.8.5/packages/python/kreuzberg/_internal_bindings.pyi
class OcrConfigRequest(BaseModel):
    backend: str = "tesseract" # Default
    language: str = "eng+deu+fra+ita+spa+por+nld"


class HierarchyConfigRequest(BaseModel):
    enabled: bool = False


class PdfOptionsRequest(BaseModel):
    extract_images: bool = True
    extract_metadata: bool = False
    hierarchy: HierarchyConfigRequest = HierarchyConfigRequest()


class ImagesConfigRequest(BaseModel):
    extract_images: bool = True # Default
    target_dpi: int = 100
    max_image_dimension: int = 2048
    max_dpi: int = 300
    auto_adjust_dpi: bool = True # Default
    inject_placeholders: bool = True


class PagesConfigRequest(BaseModel):
    extract_pages: bool = True
    insert_page_markers: bool = True
    marker_format: str = "\n\n--- Page {page_num} ---\n\n" # Default


class ExtractionConfigRequest(BaseModel):
    use_cache: bool = False
    ocr: OcrConfigRequest = OcrConfigRequest()
    pdf_options: PdfOptionsRequest = PdfOptionsRequest()
    images: ImagesConfigRequest = ImagesConfigRequest()
    pages: PagesConfigRequest = PagesConfigRequest()


def build_extraction_config(
    req: ExtractionConfigRequest | None = None,
) -> ExtractionConfig:
    if req is None:
        req = ExtractionConfigRequest()
    return ExtractionConfig(
        output_format="markdown",
        use_cache=req.use_cache,
        result_format="element_based",
        ocr=OcrConfig(
            backend=req.ocr.backend,
            language=req.ocr.language,
        ),
        pdf_options=PdfConfig(
            extract_images=req.pdf_options.extract_images,
            extract_metadata=req.pdf_options.extract_metadata,
            hierarchy=HierarchyConfig(
                enabled=req.pdf_options.hierarchy.enabled,
            ),
        ),
        images=ImageExtractionConfig(
            extract_images=req.images.extract_images,
            target_dpi=req.images.target_dpi,
            max_image_dimension=req.images.max_image_dimension,
            max_dpi=req.images.max_dpi,
            auto_adjust_dpi=req.images.auto_adjust_dpi,
        ),
        pages=PageConfig(
            extract_pages=req.pages.extract_pages,
            insert_page_markers=req.pages.insert_page_markers,
            marker_format=req.pages.marker_format,
        ),
    )


async def process_file(
    file: UploadFile,
    config_request: ExtractionConfigRequest | None = None,
) -> StreamingResponse:
    """Process any supported file and return ZIP with markdown and images."""
    config = build_extraction_config(config_request)

    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        filename = file.filename or "document"
        file_path = tmpdir / filename
        file_path.write_bytes(await file.read())

        result = await extract_file(str(file_path), config=config)

        out_dir = tmpdir / "output"
        img_dir = out_dir
        img_dir.mkdir(parents=True, exist_ok=True)

        md_path = out_dir / "content_markdown.md"
        md_path.write_text(result.content, encoding="utf-8")

        if result.images:
            for idx, img in enumerate(result.images):
                if img.get("data"):
                    ext = img.get("format", "png")
                    image_filename = f"image_{img.get("image_index", idx)}"
                    img_path = img_dir / f"{image_filename}.{ext}"
                    img_path.write_bytes(img["data"])
                    # Write ocr results as seperate file in zip `{image_filename}_ocr.md`
                    if (ocr_result :=img.get("ocr_result")):
                        (out_dir/Path(f"{image_filename}_ocr.md")).write_text(ocr_result.content)


        if result.metadata:
            metadata_path = out_dir / "metadata.md"
            metadata_path.write_text(json.dumps(result.metadata, indent=2))

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out_dir.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(out_dir.parent))
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": make_content_disposition(Path(filename).stem)
            },
        )
