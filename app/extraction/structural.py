"""
Level 2: Structural Parser (Document AI OCR/Form Parser equivalent)

This module understands document geometry:
- Bounding boxes (X, Y coordinates of words)
- Layout (tables, checkboxes, form fields)
- Spatial relationships between elements

Unlike basic OCR, this parser recognizes structure, not just text.
"""
import logging
from typing import Optional, Dict, List, Tuple, Any
import os

logger = logging.getLogger(__name__)


def extract_structural_fields(file_path: str, ocr_text: str) -> Dict[str, Any]:
    """
    Extract invoice fields using structural analysis (geometry + layout).
    
    This is Level 2 extraction - understands tables, bounding boxes, and layout.
    
    Args:
        file_path: Path to the file (PDF or image) (for geometry analysis)
        ocr_text: Raw OCR text from Level 1 (for fallback)
    
    Returns:
        Dictionary with extracted fields (same structure as rule_based.py)
        Returns empty dict if structural extraction fails.
    """
    if not os.path.exists(file_path):
        logger.warning(f"File not found for structural analysis: {file_path}")
        return {}
    
    # Structural extraction works best with PDFs
    # For images, we can't extract tables/geometry easily, so return empty
    # (Level 1.5 rule-based extraction will handle images)
    from app.image_extraction import is_image_file
    if is_image_file(file_path):
        logger.debug(f"Structural extraction skipped for image file: {file_path}")
        return {}
    
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available for structural extraction")
        return {}
    
    result = {}
    
    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0:
                return {}
            
            # Analyze first page (most invoices are single-page)
            page = pdf.pages[0]
            
            # Extract tables (structural understanding)
            tables = page.extract_tables()
            if tables:
                logger.info(f"Found {len(tables)} table(s) in PDF - using structural analysis")
                table_fields = _extract_from_tables(tables)
                result.update(table_fields)
            
            # Extract words with bounding boxes (geometry)
            words = page.extract_words()
            if words:
                logger.info(f"Found {len(words)} words with bounding boxes - analyzing layout")
                geometry_fields = _extract_from_geometry(words, ocr_text)
                # Merge results (geometry can supplement table extraction)
                for key, value in geometry_fields.items():
                    if key not in result or result[key] is None:
                        result[key] = value
            
            # Extract checkboxes and form fields
            form_fields = _extract_form_fields(page, words)
            if form_fields:
                result.update(form_fields)
            
            logger.info(f"Structural extraction completed: {len([v for v in result.values() if v is not None])} fields found")
            return result
            
    except Exception as e:
        logger.error(f"Structural extraction failed: {e}", exc_info=True)
        return {}


def _extract_from_tables(tables: List[List[List[Optional[str]]]]) -> Dict[str, Optional[str]]:
    """
    Extract invoice fields from PDF tables using structural understanding.
    
    Tables are recognized as structured data, not just text patterns.
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
    
    for table in tables:
        if not table or len(table) == 0:
            continue
        
        # Convert table to key-value pairs (structural understanding)
        # Look for patterns like: ["Subtotal", "", "$1,798.39"]
        # or: ["Total", "USD", "$1,879.32"]
        
        for row in table:
            if not row or len(row) < 2:
                continue
            
            # Clean row values
            row_clean = [str(cell).strip() if cell else "" for cell in row]
            row_lower = [cell.lower() for cell in row_clean]
            
            # Find label and value pairs
            label = row_clean[0] if len(row_clean) > 0 else ""
            value = row_clean[-1] if len(row_clean) > 1 else ""
            
            label_lower = label.lower()
            
            # Match structural patterns (not just regex - understands table structure)
            if "invoice" in label_lower and ("number" in label_lower or "#" in label_lower or "no" in label_lower):
                if not result["invoice_number"] and value:
                    result["invoice_number"] = value.strip()
            
            elif "date" in label_lower and ("invoice" in label_lower or "billing" in label_lower):
                if not result["invoice_date"] and value:
                    date_str = _normalize_date(value)
                    if date_str:
                        result["invoice_date"] = date_str
            
            elif "subtotal" in label_lower or "sub total" in label_lower:
                if not result["subtotal"] and value:
                    amount = _normalize_amount(value)
                    if amount:
                        result["subtotal"] = amount
            
            elif "tax" in label_lower and "vat" not in label_lower:
                if not result["tax"] and value:
                    amount = _normalize_amount(value)
                    if amount:
                        result["tax"] = amount
            
            elif "vat" in label_lower:
                if not result["vat"] and value:
                    amount = _normalize_amount(value)
                    if amount:
                        result["vat"] = amount
            
            elif "total" in label_lower and ("due" in label_lower or "amount" in label_lower or label_lower == "total"):
                if not result["total"] and value:
                    amount = _normalize_amount(value)
                    if amount:
                        result["total"] = amount
            
            elif "currency" in label_lower or "curr" in label_lower:
                if not result["currency"] and value:
                    currency = _extract_currency_code(value)
                    if currency:
                        result["currency"] = currency
    
    return result


def _extract_from_geometry(words: List[Dict[str, Any]], ocr_text: str) -> Dict[str, Optional[str]]:
    """
    Extract fields using bounding box geometry (X, Y coordinates).
    
    Understands spatial relationships: "Total" near a number = total amount.
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
    
    if not words:
        return result
    
    # Group words by approximate Y position (lines)
    from collections import defaultdict
    lines = defaultdict(list)
    
    for word in words:
        if not word.get('text'):
            continue
        # Round Y position to group words on same line
        y_pos = round(word.get('top', 0) / 5) * 5
        lines[y_pos].append(word)
    
    # Analyze spatial relationships
    # Look for "Total" label and find amount nearby (same line or next line)
    for y_pos in sorted(lines.keys()):
        line_words = lines[y_pos]
        line_text = " ".join([w.get('text', '') for w in line_words]).lower()
        
        # Check for "total" keyword
        if "total" in line_text or "amount due" in line_text:
            # Find amount on same line or nearby
            for word in line_words:
                text = word.get('text', '')
                amount = _normalize_amount(text)
                if amount:
                    if not result["total"]:
                        result["total"] = amount
                        break
        
        # Check for "subtotal"
        if "subtotal" in line_text or "sub total" in line_text:
            for word in line_words:
                text = word.get('text', '')
                amount = _normalize_amount(text)
                if amount:
                    if not result["subtotal"]:
                        result["subtotal"] = amount
                        break
        
        # Check for "tax"
        if "tax" in line_text and "vat" not in line_text:
            for word in line_words:
                text = word.get('text', '')
                amount = _normalize_amount(text)
                if amount:
                    if not result["tax"]:
                        result["tax"] = amount
                        break
        
        # Check for "vat"
        if "vat" in line_text:
            for word in line_words:
                text = word.get('text', '')
                amount = _normalize_amount(text)
                if amount:
                    if not result["vat"]:
                        result["vat"] = amount
                        break
    
    # Vendor name is usually in top-left region (first few lines)
    top_lines = sorted(lines.keys())[:5]
    for y_pos in top_lines:
        line_words = lines[y_pos]
        line_text = " ".join([w.get('text', '') for w in line_words])
        
        # Skip common header words
        if any(skip in line_text.lower() for skip in ['invoice', 'click to edit', 'date', 'number']):
            continue
        
        # Look for company-like text (title case, reasonable length)
        if len(line_text) > 3 and len(line_text) < 50:
            if line_text[0].isupper() and not line_text.isupper():
                if not result["vendor_name"]:
                    result["vendor_name"] = line_text.strip()
                    break
    
    return result


def _extract_form_fields(page: Any, words: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """
    Extract checkboxes and form fields (structural understanding).
    
    Recognizes that a checkbox is "checked" vs "unchecked" (geometry-based).
    """
    result = {}
    
    # pdfplumber doesn't directly support checkbox detection,
    # but we can look for checkbox-like patterns in the text
    # For full checkbox detection, would need image analysis or specialized libraries
    
    # For now, return empty (can be extended with image processing)
    return result


def _normalize_amount(amount_str: str) -> Optional[str]:
    """Normalize amount string to decimal format."""
    if not amount_str:
        return None
    
    import re
    from decimal import Decimal, InvalidOperation
    
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[$€£¥₹,\s]', '', str(amount_str))
    
    try:
        decimal_value = Decimal(cleaned)
        return str(decimal_value.quantize(Decimal('0.01')))
    except (InvalidOperation, ValueError):
        return None


def _normalize_date(date_str: str) -> Optional[str]:
    """Normalize date to ISO format (YYYY-MM-DD)."""
    if not date_str:
        return None
    
    import re
    from datetime import datetime
    
    # Common date patterns
    patterns = [
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',  # YYYY-MM-DD
        r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',  # DD/MM/YYYY or MM/DD/YYYY
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                if len(match.group(1)) == 4:
                    year, month, day = match.groups()
                else:
                    part1, part2, year = match.groups()
                    if int(part1) > 12:
                        day, month = part1, part2
                    else:
                        month, day = part1, part2
                
                month = month.zfill(2)
                day = day.zfill(2)
                date_str_iso = f"{year}-{month}-{day}"
                datetime.strptime(date_str_iso, "%Y-%m-%d")
                return date_str_iso
            except (ValueError, IndexError):
                continue
    
    return None


def _extract_currency_code(text: str) -> Optional[str]:
    """Extract currency code from text."""
    if not text:
        return None
    
    import re
    
    text_upper = text.upper()
    currency_codes = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'INR']
    
    for code in currency_codes:
        if code in text_upper:
            return code
    
    currency_symbols = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
    }
    
    for symbol, code in currency_symbols.items():
        if symbol in text:
            return code
    
    return None

