from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Invoice, InvoiceStatus
from app.config import settings
from app.extraction.rule_based import extract_invoice_fields

def compute_backoff_minutes(attempt_count: int) -> int:
    # attempt_count is incremented before scheduling
    return min(2 ** max(attempt_count - 1, 0), 60)  # cap at 60 minutes

def pick_next_ocr_job(db: Session) -> Invoice | None:
    now = datetime.utcnow()
    return (
        db.query(Invoice)
        .filter(Invoice.status.in_([InvoiceStatus.RECEIVED, InvoiceStatus.FAILED_RETRYABLE]))
        .filter(Invoice.next_attempt_at <= now)
        .order_by(Invoice.created_at.asc())
        .first()
    )

def mark_retry(db: Session, inv: Invoice, error: str):
    inv.attempt_count += 1
    inv.last_error = error

    if inv.attempt_count >= settings.max_attempts:
        inv.status = InvoiceStatus.FAILED_FINAL
        inv.next_attempt_at = datetime.utcnow()
    else:
        inv.status = InvoiceStatus.FAILED_RETRYABLE
        minutes = compute_backoff_minutes(inv.attempt_count)
        inv.next_attempt_at = datetime.utcnow() + timedelta(minutes=minutes)

    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)

def mark_ocr_pending(db: Session, inv: Invoice):
    inv.status = InvoiceStatus.OCR_PENDING
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)

def mark_ocr_done(db: Session, inv: Invoice, ocr_text: str = ""):
    inv.status = InvoiceStatus.OCR_DONE
    if ocr_text:
        inv.ocr_text = ocr_text
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)


def pick_next_extraction_job(db: Session) -> Invoice | None:
    """Pick the next invoice that needs field extraction."""
    now = datetime.utcnow()
    return (
        db.query(Invoice)
        .filter(Invoice.status == InvoiceStatus.OCR_DONE)
        .filter(Invoice.ocr_text.isnot(None))  # Must have OCR text
        .filter(Invoice.extracted_fields.is_(None))  # Not yet extracted
        .order_by(Invoice.created_at.asc())
        .first()
    )


def mark_extracted(db: Session, inv: Invoice, extracted_fields: dict):
    """Mark invoice as successfully extracted."""
    inv.status = InvoiceStatus.EXTRACTED
    inv.extracted_fields = extracted_fields
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)


def mark_extraction_failed(db: Session, inv: Invoice, error: str):
    """Mark invoice extraction as failed."""
    inv.status = InvoiceStatus.EXTRACTION_FAILED
    inv.last_error = error
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)

