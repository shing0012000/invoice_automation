"""
PDF text extraction module.
Uses PyPDF2 for rule-based text extraction (no ML/AI).

Note: This only works for text-based PDFs. Scanned/image-based PDFs
will return None and should be handled by the caller.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_path: str) -> Optional[str]:
    """
    Extract text from PDF file using PyPDF2.
    
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
    try:
        import PyPDF2
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Check if PDF is encrypted
            if pdf_reader.is_encrypted:
                logger.warning("PDF is encrypted - cannot extract text")
                return None
            
            # Extract text from all pages
            text_parts = []
            total_pages = len(pdf_reader.pages)
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(page_text.strip())
                        logger.debug(f"Extracted {len(page_text)} characters from page {page_num + 1}")
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    continue
            
            if text_parts:
                full_text = "\n\n".join(text_parts)
                logger.info(f"Successfully extracted text from {len(text_parts)}/{total_pages} page(s) ({len(full_text)} total characters)")
                return full_text
            else:
                logger.warning(f"No text extracted from PDF ({total_pages} pages) - file may be image-based (scanned) or contain no extractable text")
                return None
                
    except ImportError:
        logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
        return None
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None

