"""
Unified text extraction module.

Handles both PDF files and image files (PNG, JPEG, TIFF, etc.).
Automatically detects file type and uses appropriate extraction method.
"""
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str, content_type: Optional[str] = None) -> Optional[str]:
    """
    Extract text from a file (PDF or image).
    
    Automatically detects file type and uses appropriate extraction method:
    - PDF files: Uses pdfplumber/PyPDF2
    - Image files: Uses Tesseract OCR (pytesseract) or EasyOCR
    
    Args:
        file_path: Path to the file
        content_type: MIME type (optional, helps with detection)
    
    Returns:
        Extracted text as string, or None if:
        - File is not a supported format
        - Extraction fails
        - File is corrupted
    """
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return None
    
    # Check if it's an image file
    from app.image_extraction import is_image_file, extract_text_from_image, extract_text_from_image_easyocr
    
    if is_image_file(file_path, content_type):
        logger.info(f"Detected image file: {file_path}")
        
        # Try Tesseract OCR first (faster, more accurate)
        text = extract_text_from_image(file_path)
        if text:
            return text
        
        # Fallback to EasyOCR if Tesseract fails or is not available
        logger.info("Tesseract OCR failed or unavailable, trying EasyOCR...")
        text = extract_text_from_image_easyocr(file_path)
        if text:
            return text
        
        logger.warning(f"Could not extract text from image: {file_path}")
        return None
    
    # Check if it's a PDF file
    try:
        with open(file_path, 'rb') as f:
            header = f.read(4)
            if header == b'%PDF':
                logger.info(f"Detected PDF file: {file_path}")
                from app.pdf_extraction import extract_text_from_pdf
                return extract_text_from_pdf(file_path)
    except Exception as e:
        logger.debug(f"Error checking PDF header: {e}")
    
    # Unknown file type
    logger.warning(f"Unsupported file type: {file_path} (content_type: {content_type})")
    return None


def is_supported_file_type(file_path: str, content_type: Optional[str] = None) -> bool:
    """
    Check if a file type is supported (PDF or image).
    
    Args:
        file_path: Path to the file
        content_type: MIME type (optional)
    
    Returns:
        True if file type is supported, False otherwise
    """
    from app.image_extraction import is_image_file
    
    # Check if it's an image
    if is_image_file(file_path, content_type):
        return True
    
    # Check if it's a PDF
    try:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if header == b'%PDF':
                    return True
    except Exception:
        pass
    
    return False

