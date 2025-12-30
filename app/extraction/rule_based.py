"""
Rule-based invoice field extraction.

This module extracts structured fields from OCR text using regex patterns
and string heuristics. No ML or external services are used.
"""
import re
from datetime import datetime
from typing import Optional
from decimal import Decimal, InvalidOperation


def extract_invoice_fields(ocr_text: str) -> dict:
    """
    Extract invoice fields from OCR text using rule-based patterns.
    
    Returns a dictionary with the following keys (all nullable):
    - invoice_number: str | None
    - invoice_date: str | None (ISO format YYYY-MM-DD)
    - vendor_name: str | None
    - subtotal: str | None (decimal as string)
    - tax: str | None (decimal as string)
    - vat: str | None (decimal as string)
    - total: str | None (decimal as string)
    - currency: str | None (3-letter code or symbol)
    
    If extraction fails for a field, it returns None for that field.
    The function never raises exceptions - it's designed to be safe.
    """
    if not ocr_text or not ocr_text.strip():
        return _empty_result()
    
    # Normalize text: remove extra whitespace, make case-insensitive matching easier
    text = ocr_text.strip()
    text_lower = text.lower()
    
    result = {
        "invoice_number": _extract_invoice_number(text, text_lower),
        "invoice_date": _extract_invoice_date(text, text_lower),
        "vendor_name": _extract_vendor_name(text, text_lower),
        "subtotal": _extract_subtotal(text, text_lower),
        "tax": _extract_tax(text, text_lower),
        "vat": _extract_vat(text, text_lower),
        "total": _extract_total(text, text_lower),
        "currency": _extract_currency(text, text_lower),
    }
    
    return result


def _empty_result() -> dict:
    """Return empty result with all fields as None."""
    return {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "subtotal": None,
        "tax": None,
        "vat": None,
        "total": None,
        "currency": None,
    }


def _extract_invoice_number(text: str, text_lower: str) -> Optional[str]:
    """Extract invoice number using common patterns."""
    # Patterns: "Invoice No: 12345", "Invoice # INV-001", "Inv. Number: 456"
    patterns = [
        r'invoice\s*(?:no|number|#)\s*:?\s*([A-Z0-9\-]+)',
        r'inv\.?\s*(?:no|number|#)\s*:?\s*([A-Z0-9\-]+)',
        r'invoice\s+([A-Z0-9\-]{3,})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value and len(value) >= 2:  # Minimum reasonable length
                return value.upper()
    
    return None


def _extract_invoice_date(text: str, text_lower: str) -> Optional[str]:
    """Extract invoice date and normalize to ISO format (YYYY-MM-DD)."""
    # Common date patterns
    # YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, DD.MM.YYYY
    date_patterns = [
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',  # YYYY-MM-DD or YYYY/MM/DD
        r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',  # DD/MM/YYYY or MM/DD/YYYY
    ]
    
    # Look for date near keywords like "date", "invoice date", "issued"
    date_keywords = ['date', 'issued', 'invoice date', 'billing date']
    
    for keyword in date_keywords:
        # Find keyword and look for date nearby (within 50 chars)
        keyword_pos = text_lower.find(keyword)
        if keyword_pos != -1:
            context = text[max(0, keyword_pos):keyword_pos + 100]
            for pattern in date_patterns:
                match = re.search(pattern, context)
                if match:
                    try:
                        if len(match.group(1)) == 4:  # YYYY-MM-DD format
                            year, month, day = match.groups()
                        else:  # DD/MM/YYYY or MM/DD/YYYY
                            # Try both interpretations, prefer DD/MM/YYYY
                            part1, part2, year = match.groups()
                            # Heuristic: if part1 > 12, it's likely DD/MM
                            if int(part1) > 12:
                                day, month = part1, part2
                            else:
                                # Ambiguous - try MM/DD first
                                month, day = part1, part2
                        
                        # Normalize to 2 digits
                        month = month.zfill(2)
                        day = day.zfill(2)
                        
                        # Validate and convert to ISO
                        date_str = f"{year}-{month}-{day}"
                        datetime.strptime(date_str, "%Y-%m-%d")  # Validate
                        return date_str
                    except (ValueError, IndexError):
                        continue
    
    return None


def _extract_vendor_name(text: str, text_lower: str) -> Optional[str]:
    """Extract vendor/supplier name (usually near top of invoice)."""
    # Look for common vendor indicators in first 500 chars
    header = text[:500]
    
    # Patterns: "From:", "Vendor:", "Supplier:", "Bill From:"
    vendor_patterns = [
        r'(?:from|vendor|supplier|bill\s+from)\s*:?\s*([A-Z][A-Za-z\s&.,-]{2,30}?)(?:\n|$)',
    ]
    
    for pattern in vendor_patterns:
        match = re.search(pattern, header, re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip()
            # Clean up common artifacts and stop at common keywords
            name = re.sub(r'\s+', ' ', name)
            # Remove trailing words that are likely not part of company name
            name = re.sub(r'\s+(subtotal|total|date|invoice).*$', '', name, flags=re.IGNORECASE)
            if len(name) >= 2 and len(name) <= 100:
                return name.title()
    
    # Fallback: look for company-like text in first few lines (but be more careful)
    lines = header.split('\n')[:10]
    skip_patterns = [
        r'click\s+to\s+edit',
        r'invoice',
        r'^[|]',  # Table separators
        r'^\s*$',  # Empty lines
        r'^\d+',  # Lines starting with numbers
        r'\d{4}[-/]\d',  # Dates
        r'(billed\s+to|from|date|invoice|total|subtotal|tax|amount)',  # Common keywords
    ]
    
    for i, line in enumerate(lines):
        line = line.strip()
        # Skip if matches any skip pattern
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
            continue
        
        # Look for company-like text (all caps or title case, reasonable length)
        if (len(line) > 3 and len(line) < 50 and 
            (line.isupper() or (line[0].isupper() and not line.islower())) and
            not re.search(r'[0-9]{4,}', line) and  # No long number sequences
            i > 0):  # Skip first line (often "INVOICE")
            return line
    
    return None


def _extract_subtotal(text: str, text_lower: str) -> Optional[str]:
    """Extract subtotal amount."""
    patterns = [
        r'subtotal\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'sub\s+total\s*:?\s*\$?\s*\$?\s*([\d,]+\.?\d*)',
        r'total\s+before\s+tax\s*:?\s*\$?\s*([\d,]+\.?\d*)',
    ]
    
    # Also handle table format: "| Subtotal | | $1,798.39 |"
    table_patterns = [
        r'[|]\s*subtotal\s*[|][^|]*[|]\s*\$?\s*([\d,]+\.?\d*)\s*[|]',
        r'[|]\s*sub\s+total\s*[|][^|]*[|]\s*\$?\s*([\d,]+\.?\d*)\s*[|]',
    ]
    
    # Try table patterns first (more specific)
    for pattern in table_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    # Then try regular patterns
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    return None


def _extract_tax(text: str, text_lower: str) -> Optional[str]:
    """Extract tax amount."""
    patterns = [
        r'tax\s*(?:\([^)]+\))?\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Handles "Tax (10%): $100"
        r'tax\s+amount\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'sales\s+tax\s*:?\s*\$?\s*([\d,]+\.?\d*)',
    ]
    
    # Also handle table format: "| Tax | | +$80.93 |" or "| Tax | | $80.93 |"
    table_patterns = [
        r'[|]\s*tax\s*[|][^|]*[|]\s*\+?\$?\s*([\d,]+\.?\d*)\s*[|]',
        r'[|]\s*tax\s+amount\s*[|][^|]*[|]\s*\$?\s*([\d,]+\.?\d*)\s*[|]',
    ]
    
    # Try table patterns first (more specific)
    for pattern in table_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    # Then try regular patterns
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    return None


def _extract_vat(text: str, text_lower: str) -> Optional[str]:
    """Extract VAT amount."""
    patterns = [
        r'vat\s*:?\s*([\d,]+\.?\d*)',
        r'vat\s+amount\s*:?\s*([\d,]+\.?\d*)',
        r'value\s+added\s+tax\s*:?\s*([\d,]+\.?\d*)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    return None


def _extract_total(text: str, text_lower: str) -> Optional[str]:
    """Extract total amount (highest priority field)."""
    # Try multiple patterns, prefer "Total" or "Amount Due"
    patterns = [
        r'total\s+due\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'amount\s+due\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'grand\s+total\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'^total\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Match "Total:" at start of line
        r'\btotal\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Match "Total:" as word boundary
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.MULTILINE)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    return None


def _extract_currency(text: str, text_lower: str) -> Optional[str]:
    """Extract currency code or symbol."""
    # Look for currency codes: USD, EUR, GBP, etc.
    currency_codes = ['usd', 'eur', 'gbp', 'cad', 'aud', 'jpy', 'cny', 'inr']
    for code in currency_codes:
        if re.search(rf'\b{code}\b', text_lower):
            return code.upper()
    
    # Look for currency symbols
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


def _normalize_amount(amount_str: str) -> Optional[str]:
    """
    Normalize amount string to decimal format.
    Removes currency symbols, commas, and converts to standard decimal.
    """
    if not amount_str:
        return None
    
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[$€£¥₹,\s]', '', amount_str)
    
    # Ensure it's a valid number
    try:
        # Try to parse as decimal
        decimal_value = Decimal(cleaned)
        # Return as string with 2 decimal places
        return str(decimal_value.quantize(Decimal('0.01')))
    except (InvalidOperation, ValueError):
        return None

