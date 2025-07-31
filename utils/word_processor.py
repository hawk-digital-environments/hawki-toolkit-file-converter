#!/usr/bin/env python3
"""
Word document to Markdown processor using pypandoc.

Features
--------
• Converts .docx and .doc files to Markdown
• Extracts embedded images
• Single-ZIP response with markdown and images
"""

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import pypandoc
from fastapi import UploadFile
from fastapi.responses import StreamingResponse


async def process_word(file: UploadFile) -> StreamingResponse:
    """Process Word document and return ZIP with markdown and images."""
    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        
        # Determine file extension
        filename = file.filename or "document"
        file_ext = Path(filename).suffix.lower()
        if file_ext not in ['.doc', '.docx']:
            raise ValueError(f"Unsupported file type: {file_ext}")
        
        # Save uploaded file
        doc_path = tmpdir / filename
        doc_path.write_bytes(await file.read())
        
        # Create output directory structure
        out_dir = tmpdir / "output"
        img_dir = out_dir / "images_word"
        img_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert to markdown with image extraction
        try:
            # Use pypandoc to convert with image extraction
            markdown_content = pypandoc.convert_file(
                str(doc_path),
                'markdown',
                extra_args=[
                    '--extract-media', str(img_dir.parent),
                    '--wrap=none',
                    '--markdown-headings=atx'
                ]
            )
            
            # Fix image paths in markdown to use relative paths
            if (img_dir.parent / "media").exists():
                # pypandoc creates a 'media' folder, rename it to our convention
                media_dir = img_dir.parent / "media"
                if media_dir.exists():
                    # Move contents from media to images_word
                    for img_file in media_dir.rglob("*"):
                        if img_file.is_file():
                            new_path = img_dir / img_file.name
                            img_file.rename(new_path)
                    
                    # Remove empty media directory
                    try:
                        media_dir.rmdir()
                    except OSError:
                        pass
                    
                    # Update markdown to use correct image paths
                    markdown_content = markdown_content.replace(
                        "](media/", "](images_word/"
                    )
            
        except RuntimeError as e:
            raise ValueError(f"Failed to convert document: {str(e)}")
        
        # Write markdown file
        md_path = out_dir / "content_markdown.md"
        md_path.write_text(markdown_content, encoding="utf-8")
        
        # Create ZIP file
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out_dir.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(out_dir.parent))
        buf.seek(0)
        
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{Path(filename).stem}.zip"'},
        )


def is_word_file(filename: str) -> bool:
    """Check if filename is a Word document."""
    if not filename:
        return False
    return Path(filename).suffix.lower() in ['.doc', '.docx']