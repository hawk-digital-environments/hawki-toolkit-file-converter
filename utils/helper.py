# utils/helper.py
import re
from urllib.parse import quote

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