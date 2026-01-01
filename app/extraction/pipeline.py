"""
Multi-Level Extraction Pipeline

Orchestrates all extraction levels with intelligent fallback:
- Level 1: Basic OCR (already done - raw text extraction)
- Level 2: Structural Parser (geometry, tables, bounding boxes)
- Level 3: Semantic Extractor (ML/LLM-based understanding)

This pipeline tries each level in order and merges results intelligently.
"""
import logging
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)


def extract_invoice_fields_multi_level(
    file_path: str,
    ocr_text: str,
    enable_level_2: bool = True,
    enable_level_3: bool = False
) -> Dict[str, Any]:
    """
    Extract invoice fields using multi-level pipeline with fallback.
    
    Pipeline:
    1. Level 1 (Basic OCR): Already done - ocr_text provided
    2. Level 2 (Structural): Understands geometry, tables, layout
    3. Level 3 (Semantic): ML/LLM-based semantic understanding
    
    Args:
        file_path: Path to file (PDF or image) (for Level 2/3 structural analysis)
        ocr_text: Raw OCR text from Level 1
        enable_level_2: Enable structural parsing (default: True)
        enable_level_3: Enable semantic extraction (default: False, requires API keys)
    
    Returns:
        Dictionary with extracted fields (same structure as rule_based.py)
        Fields are merged from all levels, with higher levels taking precedence.
    """
    result = {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "subtotal": None,
        "tax": None,
        "vat": None,
        "total": None,
        "currency": None,
    }
    
    # Level 1.5: Rule-based extraction (fallback, always runs)
    from app.extraction.rule_based import extract_invoice_fields as rule_based_extract
    
    logger.info("Starting multi-level extraction pipeline...")
    logger.info(f"  - Level 1 (OCR): Complete ({len(ocr_text)} characters)")
    logger.info(f"  - Level 2 (Structural): {'Enabled' if enable_level_2 else 'Disabled'}")
    logger.info(f"  - Level 3 (Semantic): {'Enabled' if enable_level_3 else 'Disabled'}")
    
    # Always run rule-based extraction as baseline
    rule_based_result = rule_based_extract(ocr_text)
    logger.info(f"Level 1.5 (Rule-based): Extracted {len([v for v in rule_based_result.values() if v is not None])} fields")
    result.update(rule_based_result)
    
    # Level 2: Structural parsing (geometry + tables)
    # Note: Structural parsing works best with PDFs, but can work with images if converted to PDF
    if enable_level_2:
        try:
            from app.extraction.structural import extract_structural_fields
            # Structural extraction works with PDFs; for images, we pass the file path
            # but it may only work if the image was converted or if we have PDF metadata
            structural_result = extract_structural_fields(file_path, ocr_text)
            
            if structural_result:
                logger.info(f"Level 2 (Structural): Extracted {len([v for v in structural_result.values() if v is not None])} fields")
                # Merge: structural fields override rule-based if present
                for key, value in structural_result.items():
                    if value is not None:
                        result[key] = value
            else:
                logger.debug("Level 2 (Structural): No fields extracted")
        except Exception as e:
            logger.warning(f"Level 2 (Structural) extraction failed: {e}")
            # Continue with lower-level results
    
    # Level 3: Semantic extraction (ML/LLM)
    if enable_level_3:
        try:
            from app.extraction.semantic import extract_semantic_fields
            semantic_result = extract_semantic_fields(file_path, ocr_text, structural_fields=result)
            
            if semantic_result:
                logger.info(f"Level 3 (Semantic): Extracted {len([v for v in semantic_result.values() if v is not None])} fields")
                # Merge: semantic fields override all lower levels (highest confidence)
                for key, value in semantic_result.items():
                    if value is not None:
                        result[key] = value
            else:
                logger.debug("Level 3 (Semantic): No fields extracted")
        except Exception as e:
            logger.warning(f"Level 3 (Semantic) extraction failed: {e}")
            # Continue with lower-level results
    
    # Final result summary
    extracted_count = len([v for v in result.values() if v is not None])
    logger.info(f"Multi-level extraction complete: {extracted_count}/8 fields extracted")
    
    return result


def get_extraction_level_config() -> Dict[str, bool]:
    """
    Get extraction level configuration from environment variables.
    
    Returns:
        Dictionary with enable_level_2 and enable_level_3 flags
    """
    enable_level_2 = os.getenv("ENABLE_LEVEL_2_EXTRACTION", "true").lower() == "true"
    enable_level_3 = os.getenv("ENABLE_LEVEL_3_EXTRACTION", "false").lower() == "true"
    
    # Level 3 also requires semantic extraction to be enabled
    if enable_level_3:
        enable_level_3 = os.getenv("ENABLE_SEMANTIC_EXTRACTION", "false").lower() == "true"
    
    return {
        "enable_level_2": enable_level_2,
        "enable_level_3": enable_level_3
    }

