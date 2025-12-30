import hashlib
import os
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import Invoice, InvoiceStatus
from app.config import settings

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def ensure_storage_dir():
    os.makedirs(settings.storage_dir, exist_ok=True)

def find_existing(db: Session, email_message_id: str, sha256: str) -> Invoice | None:
    return db.query(Invoice).filter(and_(Invoice.email_message_id == email_message_id,
                                        Invoice.sha256 == sha256)).one_or_none()

def create_invoice_from_attachment(
    db: Session,
    email_message_id: str,
    sender: str,
    subject: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> Invoice:
    ensure_storage_dir()
    digest = sha256_bytes(file_bytes)

    existing = find_existing(db, email_message_id, digest)
    if existing:
        return existing

    # Generate UUID as string for portability
    invoice_id = str(uuid.uuid4())
    storage_path = os.path.join(settings.storage_dir, f"{invoice_id}")
    # keep extension if present
    if "." in filename:
        storage_path += "." + filename.split(".")[-1].lower()

    # Save file by UUID filename to avoid collisions
    inv = Invoice(
        id=invoice_id,
        email_message_id=email_message_id,
        sender=sender,
        subject=subject,
        filename=filename,
        content_type=content_type,
        sha256=digest,
        storage_path=storage_path,
        status=InvoiceStatus.RECEIVED,
        received_at=datetime.utcnow(),
        next_attempt_at=datetime.utcnow(),
    )
    db.add(inv)
    db.flush()  # get inv.id

    # Write file to disk
    # Ensure directory exists
    os.makedirs(os.path.dirname(storage_path) if os.path.dirname(storage_path) else '.', exist_ok=True)
    
    # Use absolute path for storage to avoid issues on Render
    abs_storage_path = os.path.abspath(storage_path)
    
    with open(abs_storage_path, "wb") as f:
        f.write(file_bytes)
    
    # Verify file was written correctly
    written_size = os.path.getsize(abs_storage_path) if os.path.exists(abs_storage_path) else 0
    if written_size != len(file_bytes):
        raise IOError(f"File size mismatch: wrote {written_size} bytes, expected {len(file_bytes)} bytes")
    
    # Store absolute path in database for consistency across environments
    inv.storage_path = abs_storage_path

    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    return inv

def update_status(db: Session, inv: Invoice, status: InvoiceStatus, error: str = ""):
    inv.status = status
    inv.last_error = error
    inv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inv)
    return inv

