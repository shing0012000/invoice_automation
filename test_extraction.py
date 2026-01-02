#!/usr/bin/env python3
"""
Test script for invoice extraction pipeline.

Tests the full extraction pipeline with a real invoice file.
"""
import os
import sys
import logging
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_extraction_with_file(file_path: str):
    """Test extraction with a real invoice file."""
    from app.text_extraction import extract_text_from_file, is_supported_file_type
    from app.extraction.pipeline import extract_invoice_fields_multi_level, get_extraction_level_config
    
    logger.info("=" * 70)
    logger.info("TESTING INVOICE EXTRACTION PIPELINE")
    logger.info("=" * 70)
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    logger.info(f"Testing with file: {file_path}")
    logger.info(f"File exists: {os.path.exists(file_path)}")
    logger.info(f"File size: {os.path.getsize(file_path)} bytes")
    
    # Step 1: Extract text (OCR)
    logger.info("\n" + "=" * 70)
    logger.info("STEP 1: Text Extraction (OCR)")
    logger.info("=" * 70)
    
    if not is_supported_file_type(file_path):
        logger.error(f"Unsupported file type: {file_path}")
        return False
    
    ocr_text = extract_text_from_file(file_path)
    
    if not ocr_text:
        logger.error("Text extraction failed - no text extracted")
        return False
    
    logger.info(f"✓ Text extraction successful: {len(ocr_text)} characters")
    logger.info(f"First 200 chars: {ocr_text[:200]}...")
    
    # Step 2: Multi-level extraction
    logger.info("\n" + "=" * 70)
    logger.info("STEP 2: Multi-Level Field Extraction")
    logger.info("=" * 70)
    
    level_config = get_extraction_level_config()
    logger.info(f"Level 2 (Structural): {level_config['enable_level_2']}")
    logger.info(f"Level 3 (Semantic/Gemini): {level_config['enable_level_3']}")
    logger.info(f"LLM Fallback: {level_config['use_llm_fallback']}")
    
    try:
        extracted_fields, confidence_status = extract_invoice_fields_multi_level(
            file_path=file_path,
            ocr_text=ocr_text,
            enable_level_2=level_config['enable_level_2'],
            enable_level_3=level_config['enable_level_3'],
            use_llm_fallback=level_config.get('use_llm_fallback', True),
            min_extraction_rate=level_config.get('min_extraction_rate', 0.5)
        )
        
        logger.info("\n" + "=" * 70)
        logger.info("EXTRACTION RESULTS")
        logger.info("=" * 70)
        logger.info(f"Confidence Status: {confidence_status.value}")
        
        # Count extracted fields
        extracted_count = 0
        for key, value in extracted_fields.items():
            if value is not None:
                # Handle confidence-wrapped values
                if isinstance(value, dict) and "value" in value:
                    actual_value = value["value"]
                    confidence = value.get("confidence", 0.0)
                    notes = value.get("notes")
                    if actual_value is not None:
                        extracted_count += 1
                        logger.info(f"  ✓ {key}: {actual_value} (confidence: {confidence:.2f})")
                        if notes:
                            logger.info(f"    Notes: {notes}")
                else:
                    extracted_count += 1
                    logger.info(f"  ✓ {key}: {value}")
            else:
                logger.info(f"  ✗ {key}: None")
        
        logger.info(f"\nTotal fields extracted: {extracted_count}/8")
        
        # Validate results
        logger.info("\n" + "=" * 70)
        logger.info("VALIDATION")
        logger.info("=" * 70)
        
        from app.extraction.pipeline import validate_accounting
        
        # Unwrap values for validation
        plain_result = {}
        for key, value in extracted_fields.items():
            if isinstance(value, dict) and "value" in value:
                plain_result[key] = value["value"]
            else:
                plain_result[key] = value
        
        is_valid, error_msg = validate_accounting(plain_result)
        
        if is_valid:
            logger.info("✓ Accounting validation PASSED")
        else:
            logger.warning(f"✗ Accounting validation FAILED: {error_msg}")
        
        logger.info("\n" + "=" * 70)
        logger.info("TEST COMPLETE")
        logger.info("=" * 70)
        
        return is_valid and extracted_count > 0
        
    except Exception as e:
        logger.error(f"Extraction failed with error: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Look for test files
    test_files = []
    
    # Check storage directory for uploaded files
    storage_dir = Path("storage")
    if storage_dir.exists():
        for ext in ["*.pdf", "*.png", "*.jpg", "*.jpeg"]:
            test_files.extend(list(storage_dir.glob(ext)))
    
    # Check root directory
    for ext in ["*.pdf", "*.png", "*.jpg", "*.jpeg"]:
        test_files.extend(list(Path(".").glob(ext)))
    
    if not test_files:
        logger.error("No test files found!")
        logger.info("Please provide a file path as argument:")
        logger.info("  python test_extraction.py <path_to_invoice_file>")
        sys.exit(1)
    
    # Use first found file or command line argument
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        test_file = str(test_files[0])
        logger.info(f"Using first found file: {test_file}")
    
    success = test_extraction_with_file(test_file)
    
    if success:
        logger.info("\n✅ TEST PASSED!")
        sys.exit(0)
    else:
        logger.error("\n❌ TEST FAILED!")
        sys.exit(1)

