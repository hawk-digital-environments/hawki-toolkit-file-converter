# utils/helper.py
import re
from urllib.parse import quote
from pathlib import Path
from PIL import Image
from fastapi import UploadFile
import io

def make_content_disposition(filename_stem: str) -> str:
    """
    Create RFC 6266 compliant Content-Disposition header for ZIP files.
    
    Args:
        filename_stem: The filename without extension (e.g., "Wölwer" for "Wölwer.pdf")
        
    Returns:
        RFC 6266 compliant Content-Disposition header value that can be encoded as latin-1
    """
    # Create the full ZIP filename
    zip_filename = f"{filename_stem}.zip"
    
    # Create ASCII fallback by removing all non-ASCII characters
    ascii_filename = ''.join(char for char in zip_filename if ord(char) < 128)
    
    # If the ASCII version is empty or too short, create a safer fallback
    if not ascii_filename or len(ascii_filename) < 4:  # At least "x.zip"
        ascii_filename = re.sub(r'[^A-Za-z0-9._-]', '_', zip_filename)
        # If still problematic, use a basic fallback
        if not ascii_filename or any(ord(char) > 127 for char in ascii_filename):
            ascii_filename = "download.zip"
    
    # URL encode the original filename for the UTF-8 version  
    utf8_encoded = quote(zip_filename.encode('utf-8'))
    
    # Build the RFC 6266 header
    header = f'attachment; filename="{ascii_filename}"'
    
    # Only add the UTF-8 version if it's different from ASCII
    if zip_filename != ascii_filename:
        header += f"; filename*=UTF-8''{utf8_encoded}"
    
    # Final safety check: ensure the header can be encoded as latin-1
    try:
        header.encode('latin-1')
    except UnicodeEncodeError:
        # If we still have issues, fall back to a simple ASCII-only header
        safe_ascii = re.sub(r'[^A-Za-z0-9._-]', '_', zip_filename)
        header = f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{utf8_encoded}'
        
    return header


def get_supported_formats()->set[str]:
    """Supported formats.
    
    Supported formats are not available dynamically via python api and
    currently need to be extracted statically by running rust. 
    Example see: https://github.com/kreuzberg-dev/kreuzberg/blob/v4.8.5/crates/kreuzberg/src/core/mime.rs#L877-L903
    """ 
    return {
        ".7z",
        ".bib",
        ".bmp",
        ".commonmark",
        ".csv",
        ".dbf",
        ".dbk",
        ".djot",
        ".doc",
        ".docbook",
        ".docbook4",
        ".docbook5",
        ".docm",
        ".docx",
        ".dot",
        ".dotm",
        ".dotx",
        ".eml",
        ".enw",
        ".epub",
        ".fb2",
        ".gif",
        ".gz",
        ".htm",
        ".html",
        ".hwp",
        ".hwpx",
        ".ipynb",
        ".j2c",
        ".j2k",
        ".jats",
        ".jb2",
        ".jbig2",
        ".jp2",
        ".jpeg",
        ".jpg",
        ".jpm",
        ".jpx",
        ".json",
        ".jsonl",
        ".key",
        ".latex",
        ".markdown",
        ".md",
        ".mdx",
        ".mj2",
        ".msg",
        ".nbib",
        ".ndjson",
        ".numbers",
        ".ods",
        ".odt",
        ".opml",
        ".org",
        ".pages",
        ".pbm",
        ".pdf",
        ".pgm",
        ".png",
        ".pnm",
        ".pot",
        ".potm",
        ".potx",
        ".ppm",
        ".ppsx",
        ".ppt",
        ".pptm",
        ".pptx",
        ".pst",
        ".ris",
        ".rst",
        ".rtf",
        ".svg",
        ".tar",
        ".tex",
        ".tgz",
        ".tif",
        ".tiff",
        ".toml",
        ".tsv",
        ".txt",
        ".typ",
        ".typst",
        ".webp",
        ".xla",
        ".xlam",
        ".xls",
        ".xlsb",
        ".xlsm",
        ".xlsx",
        ".xlt",
        ".xltx",
        ".xml",
        ".yaml",
        ".yml",
        ".zip"
    }


def get_image_file_formats():
    """The list of files to be treated as an image from supported formats."""
    return { ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".jp2", ".j2k", ".jpx", ".jpm", ".mj2", ".pbm", ".pgm", ".ppm", ".pnm" }


def get_file_type(filename: str) -> str | None:
    """Determine supported file type from filename."""
    if not filename:
        return
    
    ext = Path(filename).suffix.lower()
    
    if ext not in get_supported_formats():
        return 
    
    return ext


def is_image(file: UploadFile) -> bool:
    """Check if the file is a readable image format."""
    return get_file_type(file.filename) in get_image_file_formats()
    