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
    - discount: str | None (decimal as string, negative value)
    - tax: dict | None ({"amount": str, "type": "sales_tax" | "vat"})
    - total: str | None (decimal as string)
    - currency: str | None (3-letter code or symbol)
    
    If extraction fails for a field, it returns None for that field.
    The function never raises exceptions - it's designed to be safe.
    
    After extraction, performs reconciliation validation and inference.
    """
    if not ocr_text or not ocr_text.strip():
        return _empty_result()
    
    # Normalize text: remove extra whitespace, make case-insensitive matching easier
    text = ocr_text.strip()
    text_lower = text.lower()
    
    # Extract all fields
    result = {
        "invoice_number": _extract_invoice_number(text, text_lower),
        "invoice_date": _extract_invoice_date(text, text_lower),
        "vendor_name": _extract_vendor_name(text, text_lower),
        "subtotal": _extract_subtotal(text, text_lower),
        "discount": _extract_discount(text, text_lower),
        "tax": _extract_tax_normalized(text, text_lower),  # Returns dict with type
        "total": _extract_total(text, text_lower),
        "currency": _extract_currency(text, text_lower),
    }
    
    # Apply reconciliation logic (validate and infer missing values)
    result = _reconcile_amounts(result)
    
    # Apply field exclusivity validation
    result = _validate_field_exclusivity(result)
    
    return result


def _empty_result() -> dict:
    """Return empty result with all fields as None."""
    return {
        "invoice_number": None,
        "invoice_date": None,
        "vendor_name": None,
        "subtotal": None,
        "discount": None,
        "tax": None,
        "total": None,
        "currency": None,
    }


def _extract_invoice_number(text: str, text_lower: str) -> Optional[str]:
    """
    Extract invoice number using common patterns with negative rules.
    
    Negative rules (reject if):
    - Candidate equals known labels: "amount", "total", "subtotal", "balance", "due"
    - Contains no digits
    - Length < 3
    - Equals a column header
    
    Acceptance rules:
    - Contains ≥ 1 digit
    - Contains ≥ 1 letter (or is all digits with length >= 4)
    - Not equal to known labels
    """
    # Known labels to reject (negative rules)
    rejected_labels = {
        "amount", "total", "subtotal", "balance", "due", "tax", "vat",
        "discount", "price", "cost", "fee", "payment", "paid"
    }
    
    # Patterns: "Invoice No: 12345", "Invoice # INV-001", "Inv. Number: 456"
    patterns = [
        r'invoice\s*(?:no|number|#)\s*:?\s*([A-Z0-9\-]+)',
        r'inv\.?\s*(?:no|number|#)\s*:?\s*([A-Z0-9\-]+)',
        r'invoice\s+([A-Z0-9\-]{3,})',
    ]
    
    candidates = []
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = match.group(1).strip().upper()
            if value:
                candidates.append(value)
    
    # Score and validate candidates
    for candidate in candidates:
        # Negative rule 1: Reject if equals known label
        if candidate.lower() in rejected_labels:
            continue
        
        # Negative rule 2: Reject if length < 3
        if len(candidate) < 3:
            continue
        
        # Acceptance rule 1: Must contain at least 1 digit
        if not re.search(r'\d', candidate):
            continue
        
        # Acceptance rule 2: Must contain at least 1 letter OR be all digits with length >= 4
        has_letter = re.search(r'[A-Za-z]', candidate)
        is_all_digits = re.match(r'^\d+$', candidate)
        
        if not has_letter and not (is_all_digits and len(candidate) >= 4):
            continue
        
        # All checks passed - accept this candidate
        return candidate
    
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
    # Handle OCR errors: $ might be read as "5" or "S"
    patterns = [
        r'subtotal\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'subtotal\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error: $ -> 5
        r'subtotal\s*:?\s*S([\d,]+\.?\d*)',  # OCR error: $ -> S
        r'sub\s+total\s*:?\s*\$?\s*\$?\s*([\d,]+\.?\d*)',
        r'sub\s+total\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
        r'total\s+before\s+tax\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'total\s+before\s+tax\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
    ]
    
    # Also handle table format: "| Subtotal | | $1,798.39 |"
    table_patterns = [
        r'[|]\s*subtotal\s*[|][^|]*[|]\s*\$?\s*([\d,]+\.?\d*)\s*[|]',
        r'[|]\s*subtotal\s*[|][^|]*[|]\s*5\s+([\d,]+\.?\d*)\s*[|]',  # OCR error
        r'[|]\s*subtotal\s*[|][^|]*[|]\s*S([\d,]+\.?\d*)\s*[|]',  # OCR error
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
    # Handle OCR errors: $ might be read as "5" or "S"
    patterns = [
        r'tax\s*(?:\([^)]+\))?\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Handles "Tax (10%): $100"
        r'tax\s*(?:\([^)]+\))?\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error: $ -> 5
        r'tax\s*(?:\([^)]+\))?\s*:?\s*S([\d,]+\.?\d*)',  # OCR error: $ -> S
        r'tax\s+amount\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'tax\s+amount\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
        r'sales\s+tax\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'sales\s+tax\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
    ]
    
    # Also handle table format: "| Tax | | +$80.93 |" or "| Tax | | $80.93 |"
    table_patterns = [
        r'[|]\s*tax\s*[|][^|]*[|]\s*\+?\$?\s*([\d,]+\.?\d*)\s*[|]',
        r'[|]\s*tax\s*[|][^|]*[|]\s*\+?5\s+([\d,]+\.?\d*)\s*[|]',  # OCR error
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


def _extract_discount(text: str, text_lower: str) -> Optional[str]:
    """
    Extract discount amount and normalize as negative.
    
    Handles patterns like:
    - "Discount: -$179.84"
    - "Discount: $179.84" (assumes negative)
    - "Discount -$179.84"
    """
    patterns = [
        r'discount\s*:?\s*-?\$?\s*([\d,]+\.?\d*)',  # Handles "Discount: -$179.84" or "Discount: $179.84"
        r'discount\s+amount\s*:?\s*-?\$?\s*([\d,]+\.?\d*)',
        r'discount\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error: $ -> 5
        r'discount\s*:?\s*S([\d,]+\.?\d*)',  # OCR error: $ -> S
    ]
    
    # Table format
    table_patterns = [
        r'[|]\s*discount\s*[|][^|]*[|]\s*-?\$?\s*([\d,]+\.?\d*)\s*[|]',
        r'[|]\s*discount\s*[|][^|]*[|]\s*-?5\s+([\d,]+\.?\d*)\s*[|]',  # OCR error
    ]
    
    # Try table patterns first
    for pattern in table_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                # Normalize as negative (discounts are always negative)
                return str(-abs(Decimal(value)))
    
    # Try regular patterns
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                # Normalize as negative (discounts are always negative)
                return str(-abs(Decimal(value)))
    
    return None


def _extract_tax_normalized(text: str, text_lower: str) -> Optional[dict]:
    """
    Extract tax/VAT and normalize into single field with type.
    
    Returns:
        {"amount": str, "type": "sales_tax" | "vat"} | None
    """
    tax_amount = _extract_tax(text, text_lower)
    vat_amount = _extract_vat(text, text_lower)
    
    # Prefer VAT if both exist (VAT is more specific)
    if vat_amount:
        return {"amount": vat_amount, "type": "vat"}
    elif tax_amount:
        return {"amount": tax_amount, "type": "sales_tax"}
    
    return None


def _extract_vat(text: str, text_lower: str) -> Optional[str]:
    """Extract VAT amount (used internally by _extract_tax_normalized)."""
    patterns = [
        r'vat\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'vat\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error: $ -> 5
        r'vat\s*:?\s*S([\d,]+\.?\d*)',  # OCR error: $ -> S
        r'vat\s+amount\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'value\s+added\s+tax\s*:?\s*\$?\s*([\d,]+\.?\d*)',
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
    # Handle OCR errors: $ might be read as "5" or "S"
    patterns = [
        r'total\s+due\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'total\s+due\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error: $ -> 5
        r'total\s+due\s*:?\s*S([\d,]+\.?\d*)',  # OCR error: $ -> S
        r'amount\s+due\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'amount\s+due\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
        r'grand\s+total\s*:?\s*\$?\s*([\d,]+\.?\d*)',
        r'grand\s+total\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
        r'^total\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Match "Total:" at start of line
        r'^total\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
        r'\btotal\s*:?\s*\$?\s*([\d,]+\.?\d*)',  # Match "Total:" as word boundary
        r'\btotal\s*:?\s*5\s+([\d,]+\.?\d*)',  # OCR error
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.MULTILINE)
        if match:
            value = _normalize_amount(match.group(1))
            if value:
                return value
    
    return None


def _extract_currency(text: str, text_lower: str) -> Optional[str]:
    """
    Extract currency code or symbol.
    Handles OCR errors where $ might be read as "5" or "S".
    """
    # Look for explicit currency codes: USD, EUR, GBP, etc.
    currency_codes = ['usd', 'eur', 'gbp', 'cad', 'aud', 'jpy', 'cny', 'inr']
    for code in currency_codes:
        if re.search(rf'\b{code}\b', text_lower):
            return code.upper()
    
    # Look for currency symbols (exact match)
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
    
    # Handle OCR errors: $ might be misread as "5" or "S"
    # Look for patterns like "5 100.00" or "S100.00" (common OCR errors for "$100.00")
    # Also look for amounts with currency-like patterns
    
    # Pattern 1: "5" followed by space and number (OCR error: "$100" -> "5 100")
    # Also handle "5" directly before number without space (OCR error: "$51798" -> "551798")
    patterns_5_error = [
        r'\b5\s+[\d,]+\.[\d]{2}\b',      # "5 100.00" (with space)
        r'\b5\s*[\d,]+\.[\d]{2}\b',      # "5 100.00" or "5100.00" (flexible space)
        r'\b5\d{3,}\.\d{2}\b',           # "551798.39" (no space, large number)
    ]
    
    for pattern in patterns_5_error:
        if re.search(pattern, text):
            # Check if it's near amount keywords (total, subtotal, etc.)
            # Make context check more flexible
            amount_context_patterns = [
                r'(total|subtotal|amount|price|cost|due|fee).*?' + pattern,  # Keyword before
                pattern + r'.*?(total|subtotal|amount|due)',  # Amount before keyword
            ]
            for ctx_pattern in amount_context_patterns:
                if re.search(ctx_pattern, text_lower):
                    return 'USD'  # Most likely USD if $ is misread as 5
    
    # Pattern 2: "S" followed immediately by number (OCR error: "$100" -> "S100")
    if re.search(r'\bS[\d,]+\.[\d]{2}\b', text):
        # Make context check more flexible
        amount_context_patterns = [
            r'(total|subtotal|amount|price|cost|due|fee).*?S[\d,]+\.[\d]{2}',
            r'S[\d,]+\.[\d]{2}.*?(total|subtotal|amount|due)',
        ]
        for ctx_pattern in amount_context_patterns:
            if re.search(ctx_pattern, text_lower):
                return 'USD'
    
    # Pattern 3: Look for currency in table headers or labels
    # "Currency: USD" or "Currency USD" or "USD" near "Currency"
    currency_label_patterns = [
        r'currency\s*:?\s*(usd|eur|gbp|cad|aud|jpy|cny|inr)',
        r'(usd|eur|gbp|cad|aud|jpy|cny|inr)\s+currency',
    ]
    for pattern in currency_label_patterns:
        match = re.search(pattern, text_lower)
        if match:
            code = match.group(1).upper()
            if code in ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CNY', 'INR']:
                return code
    
    # Pattern 4: SAFER inference - only if $ symbol appears (via OCR errors)
    # Do NOT infer just from amount format - this breaks EUR/GBP invoices
    # Check if $ symbol appears (even as OCR error "5" or "S")
    has_dollar_indicator = (
        '$' in text or
        re.search(r'\b5\s+[\d,]+\.[\d]{2}\b', text) or  # OCR error: $ -> 5
        re.search(r'\bS[\d,]+\.[\d]{2}\b', text) or  # OCR error: $ -> S
        re.search(r'\b5\d{3,}\.\d{2}\b', text)  # OCR error: $ -> 5 (no space)
    )
    
    if has_dollar_indicator:
        # If we see $ indicators AND amounts in invoice context, infer USD
        usd_amount_patterns = [
            r'[\d,]+\.\d{2}',  # With commas: "1,234.56" or "51,798.39"
            r'\d+\.\d{2}',     # Without commas: "1234.56" or "51798.39"
        ]
        
        for pattern in usd_amount_patterns:
            if re.search(pattern, text):
                amount_context_patterns = [
                    r'(total|subtotal|amount|due|price|cost|fee).*?' + pattern,  # Keyword before amount
                    pattern + r'.*?(total|subtotal|amount|due)',  # Amount before keyword
                ]
                
                for ctx_pattern in amount_context_patterns:
                    if re.search(ctx_pattern, text_lower):
                        # Found amounts in invoice context with $ indicator - infer USD
                        return 'USD'
                
                # Also check if invoice keywords exist
                invoice_keywords = ['invoice', 'bill', 'payment', 'subtotal', 'total', 'amount', 'due', 'tax', 'vat']
                if any(keyword in text_lower for keyword in invoice_keywords):
                    return 'USD'
    
    # Pattern 5: If we see "5" followed by large numbers (OCR error for "$")
    # This is a common OCR error where "$51,798.39" becomes "5 51,798.39" or "551798.39"
    # Look for "5" followed by 4+ digit numbers with decimals
    if re.search(r'\b5\s*\d{4,}\.\d{2}\b', text):
        # Check if it's in invoice context
        if re.search(r'(total|subtotal|amount|due|price|cost|fee).*?5\s*\d{4,}\.\d{2}', text_lower):
            return 'USD'
    
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


def _reconcile_amounts(result: dict) -> dict:
    """
    Reconciliation logic: validate and infer missing values.
    
    Formula: subtotal - discount + tax ≈ total
    
    If inconsistent:
    - Try to infer missing tax
    - Try to infer missing discount
    - Flag as inconsistent if cannot reconcile
    """
    # Convert to Decimal for calculations
    def to_decimal(value):
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get("amount")
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
    
    subtotal = to_decimal(result.get("subtotal"))
    discount = to_decimal(result.get("discount")) or Decimal("0")  # Default to 0 if missing
    tax_dict = result.get("tax")
    tax_amount = to_decimal(tax_dict) if tax_dict else None
    tax_amount = tax_amount or Decimal("0")  # Default to 0 if missing
    total = to_decimal(result.get("total"))
    
    # Need at least subtotal and total for reconciliation
    if subtotal is None or total is None:
        return result
    
    # Calculate expected total
    expected_total = subtotal - discount + tax_amount
    
    # Tolerance for floating point errors (0.01)
    tolerance = Decimal("0.01")
    difference = abs(expected_total - total)
    
    if difference <= tolerance:
        # Reconciliation successful
        return result
    
    # Reconciliation failed - try to infer missing values
    # Case 1: Tax is missing, but we have subtotal, discount, and total
    if tax_dict is None and subtotal is not None and total is not None:
        inferred_tax = total - subtotal + discount
        if inferred_tax >= Decimal("0"):  # Tax should be non-negative
            # Infer tax type (prefer VAT if common, otherwise sales_tax)
            # Check if "vat" appears in any extracted text (we don't have access to original text here)
            tax_type = "sales_tax"  # Default
            result["tax"] = {
                "amount": str(inferred_tax.quantize(Decimal('0.01'))),
                "type": tax_type,
                "inferred": True  # Flag as inferred
            }
            return result
    
    # Case 2: Discount is missing, but we have subtotal, tax, and total
    if result.get("discount") is None and subtotal is not None and tax_amount is not None and total is not None:
        inferred_discount = subtotal + tax_amount - total
        if inferred_discount > Decimal("0"):  # Discount should be positive (we'll negate it)
            result["discount"] = str(-inferred_discount.quantize(Decimal('0.01')))
            return result
    
    # Case 3: Cannot reconcile - flag as inconsistent
    # Store reconciliation status in result (optional metadata)
    if "reconciliation_status" not in result:
        result["reconciliation_status"] = "inconsistent"
        result["reconciliation_error"] = f"Expected total: {expected_total}, Found: {total}, Difference: {difference}"
    
    return result


def _validate_field_exclusivity(result: dict) -> dict:
    """
    Apply field exclusivity validation rules.
    
    Rules:
    - Only one final total (already handled by extraction)
    - Discount must be ≤ subtotal (in absolute value)
    - Tax must be ≥ 0
    - Reject otherwise
    """
    def to_decimal(value):
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get("amount")
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
    
    # Rule 1: Discount must be ≤ subtotal (in absolute value)
    discount = to_decimal(result.get("discount"))
    subtotal = to_decimal(result.get("subtotal"))
    if discount is not None and subtotal is not None:
        if abs(discount) > subtotal:
            # Discount exceeds subtotal - reject discount
            result["discount"] = None
    
    # Rule 2: Tax must be ≥ 0
    tax_dict = result.get("tax")
    if tax_dict and isinstance(tax_dict, dict):
        tax_amount = to_decimal(tax_dict)
        if tax_amount is not None and tax_amount < Decimal("0"):
            # Negative tax - reject
            result["tax"] = None
    
    return result

