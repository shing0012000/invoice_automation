"""
Level 3: Semantic Extractor (Document AI Specialized/GenAI equivalent)

This is the highest level of extraction - understands semantic meaning:
- "Total" means "Final Balance Due" (not just a number next to a word)
- Distinguishes "Billing Address" from "Shipping Address" even if unlabeled
- Layout-agnostic: finds fields regardless of document structure

This module uses ML/LLM to understand context, not just patterns.
"""
import logging
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


def extract_semantic_fields(
    file_path: str, 
    ocr_text: str, 
    structural_fields: Dict[str, Any] = None,
    validation_error: Optional[str] = None,
    ocr_error_hint: str = ""
) -> Dict[str, Any]:
    """
    Extract invoice fields using semantic understanding (ML/LLM-based).
    
    This is Level 3 extraction - understands meaning, not just patterns.
    
    Args:
        file_path: Path to the file (PDF or image)
        ocr_text: Raw OCR text from Level 1
        structural_fields: Fields extracted by Level 2 (for context)
        validation_error: Error message from Level 2 validation (if failed)
        ocr_error_hint: Specific hint about OCR errors (e.g., '5' vs '$')
    
    Returns:
        Dictionary with extracted fields (same structure as rule_based.py)
        Returns empty dict if semantic extraction fails or is disabled.
    """
    # Check if semantic extraction is enabled
    semantic_enabled = os.getenv("ENABLE_SEMANTIC_EXTRACTION", "false").lower() == "true"
    
    if not semantic_enabled:
        logger.debug("Semantic extraction is disabled (set ENABLE_SEMANTIC_EXTRACTION=true to enable)")
        return {}
    
    # Try Google Gemini API first (if configured) - cheaper/faster than OpenAI
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        try:
            return _extract_with_gemini(ocr_text, structural_fields, validation_error, ocr_error_hint)
        except Exception as e:
            logger.warning(f"Google Gemini semantic extraction failed: {e}")
    
    # Try OpenAI API (if configured)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        try:
            return _extract_with_openai(ocr_text, structural_fields, validation_error, ocr_error_hint)
        except Exception as e:
            logger.warning(f"OpenAI semantic extraction failed: {e}")
    
    # Try Google Document AI (if configured)
    google_credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if google_credentials:
        try:
            return _extract_with_document_ai(file_path)
        except Exception as e:
            logger.warning(f"Google Document AI extraction failed: {e}")
    
    # Fallback: Use local ML model or advanced heuristics
    # For now, return empty (can be extended with local models)
    logger.debug("No semantic extraction service configured")
    return {}


def _extract_with_gemini(
    ocr_text: str, 
    structural_fields: Dict[str, Any] = None,
    validation_error: Optional[str] = None,
    ocr_error_hint: str = ""
) -> Dict[str, Any]:
    """
    Use Google Gemini to extract invoice fields with semantic understanding.
    
    Gemini is cheaper and faster than OpenAI for structured extraction tasks.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("Google Generative AI library not installed. Install with: pip install google-generativeai")
        return {}
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {}
    
    genai.configure(api_key=api_key)
    
    # Build context from structural fields if available
    context = ""
    if structural_fields:
        context = f"Previously extracted fields (may contain errors): {structural_fields}\n\n"
    
    # Add validation error context if Level 2 validation failed
    validation_context = ""
    if validation_error:
        validation_context = f"IMPORTANT: Level 2 extraction failed validation: {validation_error}\n"
        validation_context += "Please carefully re-extract fields to fix these issues.\n\n"
    
    # Add OCR error hint
    ocr_context = ocr_error_hint if ocr_error_hint else ""
    
    prompt = f"""Extract invoice fields from the following OCR text. 
Use semantic understanding to identify fields even if they're not explicitly labeled.

{context}{validation_context}{ocr_context}OCR Text:
{ocr_text[:4000]}

Note: Text truncated to 4000 characters to avoid token limits.

CRITICAL REQUIREMENTS:
1. Ensure total = subtotal - discount + tax (within 0.02 cent tolerance)
2. invoice_number must NOT be a table header like "AMOUNT", "DESCRIPTION", "QTY"
3. All critical fields (invoice_number, total, invoice_date) must be present
4. If amounts start with '5', check if it should be '$' (dollar sign) - common OCR error

Extract the following fields (return JSON only, no explanation):
- invoice_number: Invoice number or ID (NOT a table header)
- invoice_date: Invoice date in YYYY-MM-DD format
- vendor_name: Company/supplier name
- subtotal: Subtotal amount (before tax/discount)
- discount: Discount amount (negative value, or null if none)
- tax: Tax/VAT as object: {{"amount": "80.93", "type": "sales_tax"}} or {{"amount": "80.93", "type": "vat"}}
- total: Total amount due (final balance, must equal subtotal - discount + tax)
- currency: Currency code (USD, EUR, etc.)

Return only valid JSON with null for missing fields. Example:
{{"invoice_number": "INV-001", "invoice_date": "2025-12-30", "vendor_name": "Acme Corp", "subtotal": "1000.00", "discount": "-50.00", "tax": {{"amount": "100.00", "type": "sales_tax"}}, "total": "1050.00", "currency": "USD"}}
"""
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for consistent extraction
                max_output_tokens=500
            )
        )
        
        import json
        result_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        result = json.loads(result_text)
        logger.info("Google Gemini semantic extraction completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Google Gemini API call failed: {e}")
        return {}


def _extract_with_openai(
    ocr_text: str, 
    structural_fields: Dict[str, Any] = None,
    validation_error: Optional[str] = None,
    ocr_error_hint: str = ""
) -> Dict[str, Any]:
    """
    Use OpenAI GPT to extract invoice fields with semantic understanding.
    
    This understands context: "Total" = final balance, not subtotal.
    Handles OCR errors and validation failures from Level 2.
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("OpenAI library not installed. Install with: pip install openai")
        return {}
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}
    
    client = OpenAI(api_key=api_key)
    
    # Build context from structural fields if available
    context = ""
    if structural_fields:
        context = f"Previously extracted fields (may contain errors): {structural_fields}\n\n"
    
    # Add validation error context if Level 2 validation failed
    validation_context = ""
    if validation_error:
        validation_context = f"IMPORTANT: Level 2 extraction failed validation: {validation_error}\n"
        validation_context += "Please carefully re-extract fields to fix these issues.\n\n"
    
    # Add OCR error hint
    ocr_context = ocr_error_hint if ocr_error_hint else ""
    
    prompt = f"""Extract invoice fields from the following OCR text. 
Use semantic understanding to identify fields even if they're not explicitly labeled.

{context}{validation_context}{ocr_context}OCR Text:
{ocr_text[:4000]}

Note: Text truncated to 4000 characters to avoid token limits.

CRITICAL REQUIREMENTS:
1. Ensure total = subtotal - discount + tax (within 0.02 cent tolerance)
2. invoice_number must NOT be a table header like "AMOUNT", "DESCRIPTION", "QTY"
3. All critical fields (invoice_number, total, invoice_date) must be present
4. If amounts start with '5', check if it should be '$' (dollar sign) - common OCR error

Extract the following fields (return JSON only, no explanation):
- invoice_number: Invoice number or ID (NOT a table header)
- invoice_date: Invoice date in YYYY-MM-DD format
- vendor_name: Company/supplier name
- subtotal: Subtotal amount (before tax/discount)
- discount: Discount amount (negative value, or null if none)
- tax: Tax/VAT as object: {{"amount": "80.93", "type": "sales_tax"}} or {{"amount": "80.93", "type": "vat"}}
- total: Total amount due (final balance, must equal subtotal - discount + tax)
- currency: Currency code (USD, EUR, etc.)

Return only valid JSON with null for missing fields. Example:
{{"invoice_number": "INV-001", "invoice_date": "2025-12-30", "vendor_name": "Acme Corp", "subtotal": "1000.00", "discount": "-50.00", "tax": {{"amount": "100.00", "type": "sales_tax"}}, "total": "1050.00", "currency": "USD"}}
"""
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
            messages=[
                {"role": "system", "content": "You are an expert at extracting structured data from invoices. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Low temperature for consistent extraction
            max_tokens=500
        )
        
        import json
        result_text = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        result = json.loads(result_text)
        logger.info("OpenAI semantic extraction completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return {}


def _extract_with_document_ai(file_path: str) -> Dict[str, Any]:
    """
    Use Google Document AI to extract invoice fields.
    
    This is the gold standard for document understanding.
    """
    try:
        from google.cloud import documentai
    except ImportError:
        logger.warning("Google Cloud Document AI library not installed")
        return {}
    
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us")
    processor_id = os.getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID")
    
    if not all([credentials_path, project_id, processor_id]):
        logger.warning("Google Document AI not fully configured (missing credentials, project_id, or processor_id)")
        return {}
    
    try:
        client = documentai.DocumentProcessorServiceClient()
        processor_name = client.processor_path(project_id, location, processor_id)
        
        # Read file (PDF or image)
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        # Determine MIME type
        from app.image_extraction import is_image_file
        if is_image_file(file_path):
            mime_type = "image/png"  # Default, Document AI will detect actual type
        else:
            mime_type = "application/pdf"
        
        # Create request
        raw_document = documentai.RawDocument(
            content=file_content,
            mime_type=mime_type
        )
        
        request = documentai.ProcessRequest(
            name=processor_name,
            raw_document=raw_document
        )
        
        # Process document
        response = client.process_document(request=request)
        document = response.document
        
        # Extract fields from Document AI response
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
        
        # Document AI provides entities with semantic understanding
        # Map Document AI entities to our fields
        for entity in document.entities:
            entity_type = entity.type_
            entity_value = entity.text_anchor.content if entity.text_anchor else None
            
            if entity_type == "invoice_id" or entity_type == "invoice_number":
                result["invoice_number"] = entity_value
            elif entity_type == "invoice_date":
                result["invoice_date"] = entity_value
            elif entity_type == "supplier_name" or entity_type == "vendor_name":
                result["vendor_name"] = entity_value
            elif entity_type == "subtotal":
                result["subtotal"] = entity_value
            elif entity_type == "tax_amount":
                result["tax"] = entity_value
            elif entity_type == "vat_amount":
                result["vat"] = entity_value
            elif entity_type == "total_amount" or entity_type == "invoice_total":
                result["total"] = entity_value
            elif entity_type == "currency":
                result["currency"] = entity_value
        
        logger.info("Google Document AI extraction completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Google Document AI processing failed: {e}")
        return {}

