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
                
                # Diagnostic: Check PDF metadata
                try:
                    metadata = pdf.metadata
                    if metadata:
                        logger.debug(f"PDF metadata: {metadata}")
                except:
                    pass
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        # Try standard extraction first
                        page_text = page.extract_text()
                        
                        # If extract_text() returns None or empty, try extract_text_simple()
                        if not page_text or not page_text.strip():
                            try:
                                page_text = page.extract_text_simple()
                                logger.debug(f"Used extract_text_simple() for page {page_num + 1}")
                            except:
                                pass
                        
                        # Try with layout preservation
                        if not page_text or not page_text.strip():
                            try:
                                page_text = page.extract_text(layout=True)
                                logger.debug(f"Used layout=True for page {page_num + 1}")
                            except:
                                pass
                        
                        # If still empty, try extracting tables (sometimes text is in tables)
                        if not page_text or not page_text.strip():
                            try:
                                tables = page.extract_tables()
                                if tables:
                                    # Convert tables to text
                                    table_texts = []
                                    for table in tables:
                                        for row in table:
                                            if row:
                                                table_texts.append(" | ".join(str(cell) if cell else "" for cell in row))
                                    if table_texts:
                                        page_text = "\n".join(table_texts)
                                        logger.info(f"Extracted text from tables on page {page_num + 1}")
                            except Exception as e:
                                logger.debug(f"Table extraction failed for page {page_num + 1}: {e}")
                        
                        # Diagnostic: Check if page has chars attribute
                        if not page_text or not page_text.strip():
                            try:
                                chars = page.chars
                                if chars and len(chars) > 0:
                                    logger.warning(f"Page {page_num + 1} has {len(chars)} character objects but extract_text() returned empty")
                                    # Try to reconstruct text from chars
                                    if len(chars) > 0:
                                        # Group chars by approximate y position (lines)
                                        from collections import defaultdict
                                        lines = defaultdict(list)
                                        for char in chars[:100]:  # Limit to first 100 chars for performance
                                            y = round(char.get('top', 0) / 10) * 10  # Round to nearest 10
                                            lines[y].append(char.get('text', ''))
                                        reconstructed = '\n'.join(''.join(chars) for y in sorted(lines.keys()) for chars in [lines[y]])
                                        if reconstructed.strip():
                                            page_text = reconstructed
                                            logger.info(f"Reconstructed text from character objects on page {page_num + 1}")
                            except Exception as e:
                                logger.debug(f"Character extraction failed for page {page_num + 1}: {e}")
                        
                        if page_text and page_text.strip():
                            text_parts.append(page_text.strip())
                            logger.info(f"Extracted {len(page_text)} characters from page {page_num + 1} with pdfplumber")
                        else:
                            logger.debug(f"No text found on page {page_num + 1} with pdfplumber")
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
                    # Try standard extraction
                    page_text = page.extract_text()
                    
                    # If that fails, try extract_text with layout preservation
                    if not page_text or not page_text.strip():
                        try:
                            page_text = page.extract_text(extraction_mode="layout")
                            logger.debug(f"Used layout mode for page {page_num + 1}")
                        except:
                            pass
                    
                    # Try with different parameters
                    if not page_text or not page_text.strip():
                        try:
                            # Try accessing text directly from page object
                            if hasattr(page, 'get_contents'):
                                contents = page.get_contents()
                                if contents:
                                    logger.debug(f"Found contents object on page {page_num + 1}")
                        except:
                            pass
                    
                    if page_text and page_text.strip():
                        text_parts.append(page_text.strip())
                        logger.info(f"Extracted {len(page_text)} characters from page {page_num + 1} with PyPDF2")
                    else:
                        logger.debug(f"No text found on page {page_num + 1} with PyPDF2 (page type: {type(page)})")
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    continue
            
            if text_parts:
                full_text = "\n\n".join(text_parts)
                logger.info(f"Successfully extracted text with PyPDF2: {len(text_parts)}/{total_pages} page(s) ({len(full_text)} total characters)")
                return full_text
            else:
                logger.warning(f"No text extracted from PDF ({total_pages} pages) - file may be image-based (scanned) or contain no extractable text")
                
                # Diagnostic: Check PDF structure
                try:
                    # Check if PDF has text objects
                    has_text = False
                    for page in pdf_reader.pages:
                        if hasattr(page, 'get_contents'):
                            contents = page.get_contents()
                            if contents:
                                content_str = str(contents)
                                # Look for text operators
                                if '/F' in content_str or 'BT' in content_str or 'Tj' in content_str:
                                    has_text = True
                                    logger.debug(f"PDF contains text operators but extraction failed")
                                    break
                    
                    if not has_text:
                        logger.info("PDF structure analysis: No text operators found - likely image-based PDF")
                    
                    # Check for images
                    try:
                        for page_num, page in enumerate(pdf_reader.pages):
                            if '/XObject' in str(page.get_resources() if hasattr(page, 'get_resources') else ''):
                                logger.info(f"Page {page_num + 1} contains XObject (likely images)")
                    except:
                        pass
                        
                except Exception as diag_e:
                    logger.debug(f"Diagnostic check failed: {diag_e}")
                
                return None
                
    except ImportError:
        logger.error("PyPDF2 not installed. Install with: pip install PyPDF2")
        return None
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

