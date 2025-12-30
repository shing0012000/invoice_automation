"""
PDF text extraction module.
Uses multiple PDF libraries for robust text extraction (no ML/AI).

Tries pdfplumber first (better text extraction), falls back to PyPDF2.
Note: This only works for text-based PDFs. Scanned/image-based PDFs
will return None and should be handled by the caller.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> Optional[str]:
    """
    Extract text from PDF file using multiple extraction methods.
    
    Tries pdfplumber first (better at extracting text from complex PDFs),
    then falls back to PyPDF2 if pdfplumber is not available.
    
    This function extracts text from text-based PDFs only.
    For scanned/image-based PDFs, this will return None.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Extracted text as string, or None if:
        - PDF is image-based (scanned)
        - PDF is corrupted
        - Extraction fails for any reason
    """
    # Try pdfplumber first (better text extraction)
    pdfplumber_available = False
    try:
        import pdfplumber
        pdfplumber_available = True
        logger.info("pdfplumber is available")
    except ImportError:
        logger.info("pdfplumber not available, will use PyPDF2 only")
    
    if pdfplumber_available:
        try:
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Attempting extraction with pdfplumber ({total_pages} pages)")
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text_parts.append(page_text.strip())
                            logger.info(f"Extracted {len(page_text)} characters from page {page_num + 1} with pdfplumber")
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num + 1} with pdfplumber: {e}")
                        continue
                
                if text_parts:
                    full_text = "\n\n".join(text_parts)
                    logger.info(f"Successfully extracted text with pdfplumber: {len(text_parts)}/{total_pages} page(s) ({len(full_text)} total characters)")
                    return full_text
                else:
                    logger.warning(f"pdfplumber extracted no text ({total_pages} pages) - trying PyPDF2 fallback")
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}, trying PyPDF2 fallback")
            import traceback
            logger.debug(traceback.format_exc())
    
    # Fallback to PyPDF2
    try:
        import PyPDF2
        
        # Verify file exists and is readable
        import os
        if not os.path.exists(file_path):
            logger.error(f"PDF file not found: {file_path}")
            return None
        
        file_size = os.path.getsize(file_path)
        logger.info(f"Reading PDF file: {file_path} ({file_size} bytes)")
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Check if PDF is encrypted
            if pdf_reader.is_encrypted:
                logger.warning("PDF is encrypted - cannot extract text")
                return None
            
            # Extract text from all pages
            text_parts = []
            total_pages = len(pdf_reader.pages)
            logger.info(f"Attempting extraction with PyPDF2 ({total_pages} pages)")
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(page_text.strip())
                        logger.info(f"Extracted {len(page_text)} characters from page {page_num + 1} with PyPDF2")
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    continue
            
            if text_parts:
                full_text = "\n\n".join(text_parts)
                logger.info(f"Successfully extracted text with PyPDF2: {len(text_parts)}/{total_pages} page(s) ({len(full_text)} total characters)")
                return full_text
            else:
                logger.warning(f"No text extracted from PDF ({total_pages} pages) - file may be image-based (scanned) or contain no extractable text")
                # Log first 500 chars of raw PDF for debugging
                try:
                    with open(file_path, 'rb') as f:
                        raw_start = f.read(500)
                        logger.debug(f"PDF file starts with: {raw_start[:100]}...")
                except:
                    pass
                return None
                
    except ImportError:
        logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
        return None
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

