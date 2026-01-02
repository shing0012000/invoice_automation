"""
Multi-Level Extraction Pipeline

Orchestrates all extraction levels with intelligent fallback:
- Level 1: Basic OCR (already done - raw text extraction)
- Level 2: Rule-based extraction (regex patterns)
- Level 3: Semantic Extractor (ML/LLM-based understanding)

This pipeline tries each level in order and merges results intelligently.
Includes confidence scoring and status tracking for client trust indicators.
"""
import logging
import json
import re
from typing import Dict, Any, Optional, Tuple
import os
from decimal import Decimal, InvalidOperation
from app.models import ConfidenceStatus

logger = logging.getLogger(__name__)


def validate_accounting(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate accounting data from Level 2 (rule-based) extraction.
    
    Returns False (validation failed) if:
    1. total does not equal subtotal + tax - discount (allow 0.02 cent rounding margin)
    2. invoice_number is equal to common table headers like "AMOUNT", "DESCRIPTION", or "QTY"
    3. Any critical field (invoice_number, total, invoice_date) is None or empty
    
    Args:
        data: Extracted fields dictionary from Level 2
        
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    # Check 1: Critical fields must not be None or empty
    critical_fields = {
        'invoice_number': 'Invoice number',
        'total': 'Total amount',
        'invoice_date': 'Invoice date'
    }
    
    for field, label in critical_fields.items():
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, f"{label} is missing or empty"
    
    # Check 2: invoice_number must not be a table header
    invoice_number = data.get('invoice_number')
    if invoice_number:
        invoice_number_upper = str(invoice_number).upper().strip()
        rejected_headers = {'AMOUNT', 'DESCRIPTION', 'QTY', 'QUANTITY', 'TOTAL', 
                          'SUBTOTAL', 'PRICE', 'ITEM', 'UNIT', 'RATE', 'BALANCE', 'DUE'}
        if invoice_number_upper in rejected_headers:
            return False, f"Invoice number '{invoice_number}' is a table header, not a valid invoice number"
    
    # Check 3: Mathematical validation (total ≈ subtotal + tax - discount)
    def to_decimal(value):
        """Convert value to Decimal, handling confidence-wrapped fields, tax dict, and None."""
        if value is None:
            return Decimal("0")
        
        # Handle confidence-wrapped fields: {"value": ..., "confidence": ..., "notes": ...}
        if isinstance(value, dict) and "value" in value:
            value = value["value"]
        
        # Handle tax field: {"amount": str, "type": str}
        if isinstance(value, dict) and "amount" in value:
            value = value.get("amount")
        
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")
    
    subtotal = to_decimal(data.get("subtotal"))
    discount_raw = data.get("discount")
    discount = to_decimal(discount_raw) if discount_raw else Decimal("0")
    tax_dict = data.get("tax")
    tax_amount = to_decimal(tax_dict) if tax_dict else Decimal("0")
    total = to_decimal(data.get("total"))
    
    # Calculate expected total
    # Smart discount handling: Discount is stored as negative value (e.g., -179.84)
    # Formula: total = subtotal + tax + discount
    # Since discount is already negative, adding it subtracts: subtotal + tax + (-179.84) = subtotal + tax - 179.84
    # Example: subtotal=1798.39, discount=-179.84, tax=80.93
    #   → total = 1798.39 + 80.93 + (-179.84) = 1798.39 + 80.93 - 179.84 = 1699.48 ✓
    # If discount were positive (shouldn't happen), we'd need: subtotal + tax - discount
    # But since we store discount as negative, we always ADD it
    expected_total = subtotal + tax_amount + discount
    
    # Tolerance: 0.02 cents (as specified)
    tolerance = Decimal("0.02")
    difference = abs(expected_total - total)
    
    if difference > tolerance:
        return False, f"Math validation failed: total ({total}) ≠ subtotal ({subtotal}) + tax ({tax_amount}) + discount ({discount}). Expected: {expected_total}, Difference: {difference}"
    
    # All validations passed
    return True, None


def _repair_json_string(json_str: str) -> str:
    """
    Repair JSON string by handling literal escape sequences.
    
    Gemini sometimes returns JSON with literal \n characters (backslash-n as text)
    instead of actual newlines. This function converts them properly.
    
    Args:
        json_str: Raw JSON string from Gemini
        
    Returns:
        Cleaned JSON string ready for parsing
    """
    import re
    
    # The issue: Gemini returns JSON with literal \n (backslash followed by n)
    # as text characters, not actual newlines. Python's json.loads() sees these
    # as invalid escape sequences in the JSON structure.
    # 
    # Solution: Convert literal \n sequences to actual newlines, but only
    # in the JSON structure (not inside string values where they might be valid).
    
    # First, protect string values - they might contain valid escaped newlines
    # Pattern matches: "string content" including escaped quotes and newlines
    string_placeholders = []
    def replace_string(match):
        placeholder = f"__STRING_PLACEHOLDER_{len(string_placeholders)}__"
        string_placeholders.append(match.group(0))
        return placeholder
    
    # Protect all string values (quoted strings)
    protected_json = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', replace_string, json_str)
    
    # Now safely convert literal \n to actual newlines in the JSON structure
    # This handles cases like: {  "key": "value",\n  "key2": "value2"}
    protected_json = protected_json.replace('\\n', '\n')
    protected_json = protected_json.replace('\\r', '\r')  # Also handle \r
    protected_json = protected_json.replace('\\t', '\t')  # And \t
    
    # Restore protected string values
    for i, original_string in enumerate(string_placeholders):
        protected_json = protected_json.replace(f"__STRING_PLACEHOLDER_{i}__", original_string, 1)
    
    return protected_json


def call_semantic_llm(ocr_text: str, validation_failed: bool = False) -> Optional[Dict[str, Any]]:
    """
    Level 3: Semantic Extraction using Gemini 3 Flash Preview API.
    
    Uses the universal system prompt to extract invoice data with semantic understanding.
    Handles OCR errors, localization, and mathematical validation.
    
    When validation_failed is True, uses HIGH thinking_level for maximum reasoning power.
    
    Args:
        ocr_text: Raw OCR text from Level 1
        validation_failed: If True, use HIGH thinking_level for complex reasoning
        
    Returns:
        Dictionary with extracted fields, or None if extraction fails
    """
    from app.config import settings
    
    google_api_key = settings.google_api_key
    if not google_api_key:
        logger.warning("GOOGLE_API_KEY not set. Cannot use Gemini for Level 3 extraction.")
        return None
    
    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed. Install with: pip install google-generativeai")
        return None
    
    # Initialize Gemini client
    genai.configure(api_key=google_api_key)
    
    # Universal System Prompt (exact text as specified)
    system_prompt = """You are an expert accountant. Extract invoice data into JSON.

Global Logic: Always ensure Subtotal + Tax + Discount = Total. 
- If Discount is negative (e.g., -179.84), the formula is: Subtotal + Tax + (-179.84) = Subtotal + Tax - 179.84
- If Discount is positive (e.g., 179.84), treat it as negative: Subtotal + Tax - 179.84
- Discounts ALWAYS reduce the total, so in the final calculation, discount should be subtracted.
- If the OCR text has a typo (e.g., '5' instead of '$'), use math to correct it.

Localization: Handle Norwegian space separators (125 000 = 125000) and different date formats (DD/MM/YYYY vs MM/DD/YYYY) based on context.

Structure: Return ONLY valid JSON with keys: invoice_number, date, vendor_name, subtotal, tax, total, currency."""
    
    # Build the full prompt with OCR text
    prompt = f"""{system_prompt}

OCR Text:
{ocr_text[:4000]}

Note: Text truncated to 4000 characters to avoid token limits.

CRITICAL: You MUST return ALL fields. If a field is not found, use null. Do NOT return incomplete JSON.

Return ONLY valid JSON with ALL fields. Example format:
{{"invoice_number": "INV-001", "date": "2025-12-30", "vendor_name": "Acme Corp", "subtotal": "1000.00", "tax": "100.00", "total": "1100.00", "currency": "USD"}}

IMPORTANT: Return the complete JSON object with all 7 fields (invoice_number, date, vendor_name, subtotal, tax, total, currency). Use null for missing fields, but always include all keys."""
    
    try:
        # Use gemini-3-flash-preview (most stable, supports thinking_level)
        # Note: gemini-1.5-flash may not be available in all API versions
        model = genai.GenerativeModel('gemini-3-flash-preview')
        logger.debug("Using gemini-3-flash-preview model")
        
        # Configure generation config with JSON response type
        generation_config = genai.types.GenerationConfig(
            temperature=0.1,  # Low temperature for consistent extraction
            max_output_tokens=1000,  # Increased to ensure complete JSON response
            response_mime_type='application/json'  # Force JSON output (no markdown wrapping)
        )
        
        # Set thinking_level to HIGH when validation failed for maximum reasoning power
        # Note: thinking_level only works with gemini-3-flash-preview, not gemini-1.5-flash
        if validation_failed:
            try:
                generation_config.thinking_level = 'HIGH'
                logger.info("Using HIGH thinking_level for complex accounting discrepancy correction")
            except (AttributeError, TypeError):
                # thinking_level not supported by this model (e.g., gemini-1.5-flash)
                logger.debug("thinking_level not supported by this model, using standard reasoning")
        
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        result_text = response.text.strip()
        
        # Log raw response for debugging (first 500 chars)
        logger.debug(f"Gemini raw response (first 500 chars): {result_text[:500]}")
        
        # JSON Repair: Convert literal \n escape sequences to actual newlines
        # This handles cases where Gemini returns literal backslash-n characters
        # IMPORTANT: Even with response_mime_type='application/json', Gemini might still
        # return JSON with literal escape sequences that need to be converted
        original_length = len(result_text)
        result_text = _repair_json_string(result_text)
        if len(result_text) != original_length:
            logger.debug(f"JSON repair changed length: {original_length} -> {len(result_text)}")
        
        # Additional safety: If the string still contains literal backslash-n after repair,
        # it means the repair didn't work - try a more aggressive fix
        if '\\n' in result_text:
            logger.warning("JSON still contains literal \\n after repair, applying aggressive fix")
            # Use a simpler, more direct approach
            # Protect all string values
            strings = []
            def protect_string(m):
                strings.append(m.group(0))
                return f"__PROTECTED_STRING_{len(strings)-1}__"
            
            protected = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', protect_string, result_text)
            # Replace all literal escape sequences in the structure
            protected = protected.replace('\\n', '\n')
            protected = protected.replace('\\r', '\r')
            protected = protected.replace('\\t', '\t')
            # Restore strings
            for i, s in enumerate(strings):
                protected = protected.replace(f"__PROTECTED_STRING_{i}__", s, 1)
            result_text = protected
        
        # Remove markdown code blocks if present (fallback if response_mime_type didn't work)
        if result_text.startswith("```"):
            # Find the closing ```
            parts = result_text.split("```")
            if len(parts) >= 3:
                # Extract content between first and second ```
                result_text = parts[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:].strip()
            else:
                # Malformed markdown, try to extract JSON
                result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        # Try to extract JSON object if response contains other text
        # Look for first { and last } to extract JSON object
        first_brace = result_text.find('{')
        last_brace = result_text.rfind('}')
        
        if first_brace != -1:
            if last_brace != -1 and last_brace > first_brace:
                # Complete JSON object found
                result_text = result_text[first_brace:last_brace + 1]
            else:
                # Incomplete JSON - try to close it
                result_text = result_text[first_brace:]
                # Remove trailing comma if present
                result_text = re.sub(r',\s*$', '', result_text.strip())
                # Close the JSON object
                if not result_text.endswith('}'):
                    result_text = result_text.rstrip() + '\n}'
                    logger.warning("Attempted to close incomplete JSON object from Gemini response")
        
        # Clean up common JSON issues
        # Remove empty keys first (before removing trailing commas)
        # Pattern 1: Empty key with value: "": "value" or "": value
        result_text = re.sub(r',?\s*""\s*:\s*"[^"]*"', '', result_text)  # Remove "": "value"
        result_text = re.sub(r',?\s*""\s*:\s*[^,}\]]+', '', result_text)  # Remove "": value (non-string)
        # Pattern 2: Empty key before closing brace: , ""} or ""}
        result_text = re.sub(r',\s*""\s*}', '}', result_text)  # Remove , ""}
        result_text = re.sub(r'\s*""\s*}', '}', result_text)  # Remove ""}
        # Pattern 3: Empty key in middle: , "" , or , ""
        result_text = re.sub(r',\s*""\s*,', ',', result_text)  # Remove , "" ,
        result_text = re.sub(r',\s*""\s*([,}])', r'\1', result_text)  # Remove , "" before , or }
        
        # Remove trailing commas before closing braces/brackets
        result_text = re.sub(r',(\s*[}\]])', r'\1', result_text)
        
        # Fix single quotes in values (common Gemini issue)
        # Replace patterns like: "key": 'value' with "key": "value"
        result_text = re.sub(r':\s*\'([^\']*)\'', r': "\1"', result_text)
        
        # Fix unescaped newlines in string values (replace with \n)
        result_text = re.sub(r'"([^"]*)\n([^"]*)"', r'"\1\\n\2"', result_text)
        
        # Remove any control characters that might break JSON
        result_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', result_text)
        
        # Try to fix unterminated strings (basic heuristic)
        # This is a simple fix - for complex cases, we'll log and fail gracefully
        if '"' in result_text:
            # Count quotes - if odd, try to close the last string
            quote_count = result_text.count('"')
            if quote_count % 2 != 0:
                # Find the last unclosed quote and try to close it
                last_quote_pos = result_text.rfind('"')
                if last_quote_pos > 0:
                    # Check if it's inside a value (not a key)
                    before_quote = result_text[:last_quote_pos]
                    if ':' in before_quote:
                        # Likely an unclosed string value, try to close it
                        result_text = result_text[:last_quote_pos + 1] + '"' + result_text[last_quote_pos + 1:]
                        logger.warning("Attempted to fix unterminated string in Gemini response")
        
        # Parse JSON response
        # Try parsing - if it fails, the repair function might not have worked correctly
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError as parse_error:
            # If parsing fails, try one more repair pass
            # Sometimes the repair needs to be applied more aggressively
            logger.warning(f"First JSON parse attempt failed, trying additional repair...")
            result_text_before_second_repair = result_text
            result_text = _repair_json_string(result_text)  # Try repair again
            
            # Also try replacing literal backslash-n more directly
            # Check if the string actually contains the two-character sequence \ + n
            if '\\n' in result_text and '\n' not in result_text:
                # The string has literal backslash-n but no actual newlines
                # This means the repair didn't work - try a more direct approach
                logger.warning("Direct backslash-n replacement needed")
                # Protect strings and replace
                strings = []
                def save_string(m):
                    strings.append(m.group(0))
                    return f"__STR_{len(strings)-1}__"
                protected = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', save_string, result_text)
                protected = protected.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
                for i, s in enumerate(strings):
                    protected = protected.replace(f"__STR_{i}__", s, 1)
                result_text = protected
            
            try:
                result = json.loads(result_text)
                logger.info("Second JSON parse attempt succeeded after additional repair")
                # Success! Continue with the result
            except json.JSONDecodeError as parse_error2:
                # Log the problematic JSON for debugging
                logger.error(f"Gemini returned invalid JSON (after repair attempts): {parse_error2}")
                logger.error(f"Problematic JSON (full response): {result_text}")
                logger.error(f"JSON error position: line {parse_error2.lineno}, column {parse_error2.colno}")
                # Try to show the problematic area
                if parse_error2.lineno and parse_error2.colno:
                    lines = result_text.split('\n')
                    if parse_error2.lineno <= len(lines):
                        problem_line = lines[parse_error2.lineno - 1]
                        logger.error(f"Problem line: {problem_line}")
                        if parse_error2.colno <= len(problem_line):
                            logger.error(f"Problem char: '{problem_line[parse_error2.colno - 1]}' at position {parse_error2.colno}")
                raise  # Re-raise to be caught by outer exception handler
        
        # Normalize field names to match our schema
        # Gemini returns "date" but we use "invoice_date"
        normalized_result = {}
        field_mapping = {
            "invoice_number": "invoice_number",
            "date": "invoice_date",
            "vendor_name": "vendor_name",
            "subtotal": "subtotal",
            "tax": "tax",
            "discount": "discount",
            "total": "total",
            "currency": "currency"
        }
        
        for gemini_key, our_key in field_mapping.items():
            if gemini_key in result:
                value = result[gemini_key]
                # Handle tax field - convert to dict format if needed
                if our_key == "tax" and value and not isinstance(value, dict):
                    normalized_result[our_key] = {"amount": str(value), "type": "sales_tax"}
                # Handle discount - ensure negative if present
                elif our_key == "discount" and value:
                    try:
                        discount_val = Decimal(str(value))
                        if discount_val > 0:
                            normalized_result[our_key] = str(-discount_val)
                        else:
                            normalized_result[our_key] = str(discount_val)
                    except:
                        normalized_result[our_key] = str(value)
                else:
                    normalized_result[our_key] = value
        
        thinking_status = "HIGH thinking" if validation_failed else "standard"
        extracted_count = len([v for v in normalized_result.values() if v is not None])
        logger.info(f"Level 3 (Gemini 3 Flash) semantic extraction completed successfully ({thinking_status})")
        logger.info(f"Gemini extracted {extracted_count} fields: {list(normalized_result.keys())}")
        logger.debug(f"Gemini full response: {normalized_result}")
        return normalized_result
        
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        logger.debug(f"Gemini response: {result_text[:500]}")
        return None
    except Exception as e:
        error_str = str(e)
        # Check for quota/rate limit errors (429)
        if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
            logger.warning(f"Gemini API quota/rate limit exceeded: {error_str[:200]}")
            logger.warning("Level 3 (Gemini) extraction unavailable due to API quota. Falling back to rule-based extraction.")
            return None
        # Check for model not found errors (404)
        elif "404" in error_str or "not found" in error_str.lower() or "not supported" in error_str.lower():
            logger.warning(f"Gemini model not available: {error_str[:200]}")
            logger.warning("Level 3 (Gemini) extraction unavailable - model not found. Falling back to rule-based extraction.")
            return None
        else:
            logger.error(f"Gemini API call failed: {e}")
            return None


def should_use_llm(rule_based_result: Dict[str, Any], ocr_text: str, min_extraction_rate: float = 0.5) -> bool:
    """
    Decide if we should use expensive LLM extraction (smart cost optimization).
    
    Returns True only if:
    1. Critical fields are missing (currency, total)
    2. Low extraction quality (too many None values)
    3. Currency is missing but amounts are present (common OCR error case)
    
    Args:
        rule_based_result: Results from rule-based extraction
        ocr_text: Raw OCR text (for additional context checks)
        min_extraction_rate: Minimum fraction of fields that must be extracted (default: 0.5 = 50%)
    
    Returns:
        True if LLM should be used, False otherwise
    """
    # Critical fields that must be present for a complete invoice
    critical_fields = ['currency', 'total']
    missing_critical = any(rule_based_result.get(field) is None for field in critical_fields)
    
    # Count extracted fields
    extracted_count = sum(1 for v in rule_based_result.values() if v is not None)
    total_fields = len(rule_based_result)
    extraction_rate = extracted_count / total_fields if total_fields > 0 else 0.0
    
    # Use LLM if critical fields are missing
    if missing_critical:
        logger.info(f"LLM fallback triggered: Critical fields missing (extraction rate: {extraction_rate:.1%})")
        return True
    
    # Use LLM if extraction quality is too low
    if extraction_rate < min_extraction_rate:
        logger.info(f"LLM fallback triggered: Low extraction rate ({extraction_rate:.1%} < {min_extraction_rate:.1%})")
        return True
    
    # Special case: Currency is missing but we have amounts (common OCR error)
    # This is the "$" -> "5" problem - LLM can help fix this
    if rule_based_result.get('currency') is None:
        # Check if we have amounts but no currency
        has_amounts = any(rule_based_result.get(field) is not None 
                         for field in ['subtotal', 'tax', 'vat', 'total'])
        if has_amounts:
            logger.info("LLM fallback triggered: Currency missing but amounts present (likely OCR error)")
            return True
    
    # Rule-based extraction is sufficient
    logger.debug(f"Rule-based extraction sufficient ({extraction_rate:.1%} fields extracted) - skipping LLM")
    return False


def extract_invoice_fields_multi_level(
    file_path: str,
    ocr_text: str,
    enable_level_2: bool = True,
    enable_level_3: bool = False,
    use_llm_fallback: bool = True,
    min_extraction_rate: float = 0.5
) -> Dict[str, Any]:
    """
    Extract invoice fields using multi-level pipeline with smart LLM fallback.
    
    Pipeline:
    1. Level 1 (Basic OCR): Already done - ocr_text provided
    2. Level 1.5 (Rule-based): Fast, free regex-based extraction (always runs first)
    3. Level 2 (Structural): Understands geometry, tables, layout
    4. Level 3 (Semantic): ML/LLM-based semantic understanding (smart fallback only)
    
    Smart LLM Fallback Strategy:
    - Always try rule-based first (free, fast)
    - Only use expensive LLM if:
      * Critical fields missing (currency, total)
      * Low extraction quality (< 50% fields extracted)
      * Currency missing but amounts present (OCR error case)
    
    Args:
        file_path: Path to file (PDF or image) (for Level 2/3 structural analysis)
        ocr_text: Raw OCR text from Level 1
        enable_level_2: Enable structural parsing (default: True)
        enable_level_3: Enable semantic extraction capability (default: False, requires API keys)
        use_llm_fallback: Use smart fallback - only call LLM when needed (default: True)
        min_extraction_rate: Minimum extraction rate to avoid LLM (default: 0.5 = 50%)
    
    Returns:
        Tuple of:
        - Dictionary with extracted fields (includes confidence scores and notes)
        - ConfidenceStatus enum (VERIFIED, REVIEW, ERROR)
        
        Field structure includes:
        - value: The extracted value
        - confidence: float (0.0-1.0)
        - notes: Optional[str] explaining low confidence or fixes
    """
    # Helper function to wrap values with confidence metadata
    def wrap_with_confidence(value, confidence: float = 0.9, notes: Optional[str] = None):
        """Wrap extracted value with confidence metadata."""
        if value is None:
            return None
        return {
            "value": value,
            "confidence": confidence,
            "notes": notes
        }
    
    # Track if LLM was used to fix errors
    llm_fixes_applied = []
    confidence_status = ConfidenceStatus.ERROR  # Default to ERROR
    
    # Initialize result structure matching database schema (JSON field)
    result = {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "subtotal": None,
        "discount": None,
        "tax": None,  # Will be dict: {"amount": str, "type": "sales_tax"|"vat"}
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
    
    # Wrap rule-based results with confidence scores (default: 0.9 for rule-based)
    for key, value in rule_based_result.items():
        if value is not None:
            # Special handling for tax dict
            if key == "tax" and isinstance(value, dict):
                result[key] = {
                    "value": value,
                    "confidence": 0.9,
                    "notes": None
                }
            else:
                result[key] = wrap_with_confidence(value, confidence=0.9)
        else:
            result[key] = None
    
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
    
    # Extract plain values for validation (unwrap confidence wrappers)
    def unwrap_value(field_data):
        """Extract plain value from confidence-wrapped field."""
        if field_data is None:
            return None
        if isinstance(field_data, dict) and "value" in field_data:
            return field_data["value"]
        return field_data
    
    # Prepare plain result for validation
    plain_result = {k: unwrap_value(v) for k, v in result.items()}
    
    # Level 3: Semantic extraction (ML/LLM) - Smart fallback with validation
    if enable_level_3:
        # First, validate Level 2 (rule-based) results
        is_valid, validation_error = validate_accounting(plain_result)
        
        should_use_llm_now = False
        
        if not is_valid:
            # Level 2 validation failed - escalate to Level 3
            logger.info(f"Level 2 validation failed: {validation_error}. Escalating to Level 3...")
            should_use_llm_now = True
        elif use_llm_fallback:
            # Also check other fallback conditions (missing fields, low quality, etc.)
            should_use_llm_now = should_use_llm(plain_result, ocr_text, min_extraction_rate)
        
        if should_use_llm_now:
            logger.info("Using LLM semantic extraction (fallback triggered)")
            
            # Try Gemini first (direct call for Level 3)
            # Pass validation_failed=True to use HIGH thinking_level when validation failed
            gemini_result = call_semantic_llm(ocr_text, validation_failed=not is_valid)
            
            if gemini_result:
                logger.info("Level 3 (Gemini 3 Flash) extraction successful")
                semantic_result = gemini_result
            else:
                # Fallback to other semantic extraction methods
                try:
                    from app.extraction.semantic import extract_semantic_fields
                    
                    # Check for OCR error: total starting with '5' (likely '$' misread)
                    ocr_error_hint = ""
                    total_data = result.get("total")
                    total_value = unwrap_value(total_data)
                    if total_value and isinstance(total_value, str):
                        # Check if total starts with '5' and validation failed
                        if total_value.strip().startswith('5') and not is_valid:
                            ocr_error_hint = " IMPORTANT: The total amount may start with '5' which could be an OCR error where '$' was misread as '5'. Please check if amounts starting with '5' should actually be '$' (dollar sign)."
                            llm_fixes_applied.append("total: OCR error correction (5 -> $)")
                    
                    semantic_result = extract_semantic_fields(
                        file_path, 
                        ocr_text, 
                        structural_fields=plain_result,
                        validation_error=validation_error if not is_valid else None,
                        ocr_error_hint=ocr_error_hint
                    )
                except Exception as e:
                    logger.warning(f"Fallback semantic extraction failed: {e}")
                    semantic_result = None
            
            if semantic_result:
                extracted_semantic_count = len([v for v in semantic_result.values() if v is not None])
                logger.info(f"Level 3 (Semantic): Extracted {extracted_semantic_count} fields via LLM")
                
                # Merge: semantic fields override all lower levels
                # Set confidence to 0.5 for LLM-fixed fields with notes
                for key, value in semantic_result.items():
                    if value is not None:
                        # Check if this field was fixed by LLM
                        was_fixed = any(key in fix for fix in llm_fixes_applied) or not is_valid
                        
                        if was_fixed:
                            # LLM fixed this field - lower confidence with notes
                            notes = f"Level 3 (Gemini) correction applied: {validation_error}" if validation_error else "Level 3 (Gemini) extraction (validation failed)"
                            if key in ["total", "subtotal", "currency"]:
                                notes = "Level 3 (Gemini) correction: OCR error fixed (e.g., '5' -> '$')"
                            
                            result[key] = wrap_with_confidence(value, confidence=0.5, notes=notes)
                            confidence_status = ConfidenceStatus.REVIEW
                        else:
                            # LLM extraction but no fix needed - medium confidence
                            result[key] = wrap_with_confidence(value, confidence=0.7, notes="Level 3 (Gemini) extraction")
            else:
                logger.debug("Level 3 (Semantic): No fields extracted from LLM")
        else:
            # Validation passed - set to VERIFIED
            if is_valid:
                confidence_status = ConfidenceStatus.VERIFIED
                logger.info("Skipping LLM - Level 2 validation passed (VERIFIED)")
            else:
                logger.info("Skipping LLM - Level 2 validation passed (cost savings)")
    else:
        # Level 3 not enabled - check validation
        is_valid, validation_error = validate_accounting(plain_result)
        if is_valid:
            confidence_status = ConfidenceStatus.VERIFIED
        else:
            confidence_status = ConfidenceStatus.ERROR
    
    # Final result summary
    # Flatten result for database (extract values, keep confidence metadata)
    final_result = {}
    for key, field_data in result.items():
        if field_data is None:
            final_result[key] = None
        elif isinstance(field_data, dict) and "value" in field_data:
            # Keep full structure with confidence
            final_result[key] = field_data
        else:
            # Legacy format - wrap it
            final_result[key] = wrap_with_confidence(field_data, confidence=0.9)
    
    extracted_count = len([v for v in final_result.values() if v is not None])
    logger.info(f"Multi-level extraction complete: {extracted_count}/8 fields extracted, Status: {confidence_status.value}")
    
    return final_result, confidence_status


def get_extraction_level_config() -> Dict[str, Any]:
    """
    Get extraction level configuration from validated settings.
    
    Returns:
        Dictionary with:
        - enable_level_2: bool
        - enable_level_3: bool
        - use_llm_fallback: bool (smart cost optimization)
        - min_extraction_rate: float (threshold for LLM fallback)
    """
    from app.config import settings
    
    # Level 2 is enabled by default (structural parsing)
    enable_level_2 = True  # Always enabled for now
    
    # Level 3 requires BOTH enable_level_3_extraction AND enable_semantic_extraction
    # Also requires GOOGLE_API_KEY to be set
    enable_level_3 = (
        settings.enable_level_3_extraction and 
        settings.enable_semantic_extraction and
        settings.google_api_key is not None
    )
    
    # Smart LLM fallback (default: True - only use LLM when needed)
    use_llm_fallback = settings.use_llm_fallback
    
    # Minimum extraction rate threshold (default: 0.5 = 50%)
    # If rule-based extracts >= 50% of fields, skip LLM
    min_extraction_rate = settings.min_extraction_rate
    
    return {
        "enable_level_2": enable_level_2,
        "enable_level_3": enable_level_3,
        "use_llm_fallback": use_llm_fallback,
        "min_extraction_rate": min_extraction_rate
    }

