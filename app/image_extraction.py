"""
Image OCR text extraction module.

Supports PNG, JPEG, TIFF, and other image formats.
Uses Tesseract OCR (pytesseract) for text extraction from images.

This is essential for scanned invoices or images of invoices.
"""
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {
    'png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'gif', 'webp'
}

SUPPORTED_IMAGE_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/jpg', 'image/tiff', 
    'image/bmp', 'image/gif', 'image/webp'
}


def is_image_file(file_path: str, content_type: Optional[str] = None) -> bool:
    """
    Check if a file is an image based on extension or content type.
    
    Args:
        file_path: Path to the file
        content_type: MIME type (optional, for validation)
    
    Returns:
        True if file appears to be an image, False otherwise
    """
    # Check by extension
    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    if ext in SUPPORTED_IMAGE_FORMATS:
        return True
    
    # Check by content type if provided
    if content_type:
        content_type_lower = content_type.lower().split(';')[0].strip()
        if content_type_lower in SUPPORTED_IMAGE_MIME_TYPES:
            return True
    
    return False


def extract_text_from_image(file_path: str) -> Optional[str]:
    """
    Extract text from image file using OCR (Tesseract).
    
    This function handles scanned invoices or images of invoices.
    Uses pytesseract (Tesseract OCR) for text extraction.
    
    Args:
        file_path: Path to the image file
    
    Returns:
        Extracted text as string, or None if:
        - Image file is corrupted
        - OCR fails for any reason
        - Tesseract is not installed
    """
    import os
    
    # Validate file exists
    if not os.path.exists(file_path):
        logger.error(f"Image file does not exist: {file_path}")
        return None
    
    # Verify it's an image file
    if not is_image_file(file_path):
        logger.warning(f"File does not appear to be an image: {file_path}")
        return None
    
    # Try to import pytesseract
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.error(
            "pytesseract or Pillow not installed. "
            "Install with: pip install pytesseract pillow"
        )
        return None
    
    # Configure pytesseract to find Tesseract binary
    # This is especially important for conda installations and cloud platforms (Render)
    try:
        import shutil
        tesseract_cmd = shutil.which('tesseract')
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            logger.debug(f"Configured pytesseract to use: {tesseract_cmd}")
        else:
            # Fallback: try common paths (including Render's /usr/bin/tesseract)
            # Order: Render/cloud paths first, then local development paths
            tesseract_paths = [
                '/usr/bin/tesseract',  # Render/cloud platforms (installed via apt-get)
                '/usr/local/bin/tesseract',  # Common system installation
                os.path.join(os.environ.get('CONDA_PREFIX', ''), 'bin', 'tesseract'),  # Conda
                '/opt/anaconda3/envs/acctapp/bin/tesseract',  # Specific conda path
            ]
            for path in tesseract_paths:
                if path and os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    logger.info(f"Configured pytesseract to use: {path}")
                    break
            else:
                logger.warning("Could not find tesseract binary. OCR may fail. Trying EasyOCR fallback...")
    except Exception as e:
        logger.warning(f"Error configuring pytesseract path: {e}")
    
    try:
        # Open image
        logger.info(f"Opening image file: {file_path}")
        image = Image.open(file_path)
        
        # Convert to RGB if necessary (Tesseract works best with RGB)
        if image.mode != 'RGB':
            logger.debug(f"Converting image from {image.mode} to RGB")
            image = image.convert('RGB')
        
        # Perform OCR
        logger.info(f"Performing OCR on image: {file_path}")
        text = pytesseract.image_to_string(image, lang='eng')
        
        if text and text.strip():
            logger.info(f"OCR extracted {len(text)} characters from image")
            return text.strip()
        else:
            logger.warning(f"OCR returned no text from image: {file_path}")
            return None
            
    except Exception as e:
        logger.error(f"OCR extraction failed for image {file_path}: {e}", exc_info=True)
        return None


def extract_text_from_image_easyocr(file_path: str) -> Optional[str]:
    """
    Alternative OCR method using EasyOCR (if Tesseract is not available).
    
    EasyOCR is easier to install (no system dependencies) but slower.
    
    Args:
        file_path: Path to the image file
    
    Returns:
        Extracted text as string, or None if extraction fails
    """
    try:
        import easyocr
    except ImportError:
        logger.debug("EasyOCR not installed. Install with: pip install easyocr")
        return None
    
    try:
        logger.info(f"Using EasyOCR for image: {file_path}")
        reader = easyocr.Reader(['en'])  # English only
        result = reader.readtext(file_path)
        
        # Combine all detected text
        text_parts = [detection[1] for detection in result]
        text = '\n'.join(text_parts)
        
        if text and text.strip():
            logger.info(f"EasyOCR extracted {len(text)} characters from image")
            return text.strip()
        else:
            logger.warning(f"EasyOCR returned no text from image: {file_path}")
            return None
            
    except Exception as e:
        logger.error(f"EasyOCR extraction failed for image {file_path}: {e}", exc_info=True)
        return None

