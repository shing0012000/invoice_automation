from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import threading
import time
import asyncio
import uuid
import os

from app.db import Base, engine, get_db, SessionLocal
from app.schemas import InvoiceOut
from app import crud
from app.models import Invoice, InvoiceStatus
from app.config import settings
from app.worker import (
    pick_next_ocr_job, mark_ocr_pending, mark_ocr_done, mark_retry,
    pick_next_extraction_job, mark_extracted, mark_extraction_failed
)

# Configure FastAPI based on demo mode
if settings.demo_mode:
    app = FastAPI(title="Invoice Automation Demo", docs_url=None, redoc_url=None)
else:
    app = FastAPI(title="Invoice Automation MVP")

# Create tables (MVP). Later replace with Alembic migrations.
Base.metadata.create_all(bind=engine)

# Demo UI - serve static HTML at root
@app.get("/", response_class=HTMLResponse)
async def demo_ui():
    """Serve the demo UI page."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "static", "demo.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return f.read()
    else:
        # Fallback HTML if file doesn't exist
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Invoice Automation Demo</title></head>
        <body>
            <h1>Invoice Automation Demo</h1>
            <p>Demo UI file not found. Please ensure static/demo.html exists.</p>
        </body>
        </html>
        """

# Demo endpoint - public upload and extraction
@app.post("/demo/upload-invoice")
async def demo_upload_invoice(attachment: UploadFile = File(...)):
    """
    Public demo endpoint: upload invoice PDF and get extracted fields.
    Blocks until extraction is complete (suitable for demo only).
    """
    db = SessionLocal()
    try:
        # Generate a unique email message ID for demo
        email_message_id = f"demo-{uuid.uuid4().hex[:8]}"
        
        # Read file data
        data = await attachment.read()
        
        # Create invoice record
        inv = crud.create_invoice_from_attachment(
            db=db,
            email_message_id=email_message_id,
            sender="demo@example.com",
            subject="Demo Upload",
            filename=attachment.filename or "invoice.pdf",
            content_type=attachment.content_type or "application/pdf",
            file_bytes=data,
        )
        
        invoice_id = inv.id
        
        # Wait for OCR to complete (with timeout)
        max_wait = 30  # seconds
        wait_interval = 0.5
        waited = 0
        
        while waited < max_wait:
            db.refresh(inv)
            if inv.status == InvoiceStatus.OCR_DONE:
                break
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        # Wait for extraction to complete
        while waited < max_wait:
            db.refresh(inv)
            if inv.status in [InvoiceStatus.EXTRACTED, InvoiceStatus.EXTRACTION_FAILED]:
                break
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        # Refresh to get latest state
        db.refresh(inv)
        
        # Return only extracted fields (no internal IDs or metadata)
        if inv.status == InvoiceStatus.EXTRACTED and inv.extracted_fields:
            return {
                "status": "success",
                "extracted_fields": inv.extracted_fields
            }
        elif inv.status == InvoiceStatus.EXTRACTION_FAILED:
            return {
                "status": "extraction_failed",
                "error": inv.last_error or "Field extraction failed",
                "extracted_fields": inv.extracted_fields or {}
            }
        else:
            return {
                "status": "timeout",
                "error": "Processing timed out. Please try again.",
                "extracted_fields": {}
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "extracted_fields": {}
        }
    finally:
        db.close()

# Internal endpoints - only available when not in demo mode
if not settings.demo_mode:
    @app.post("/ingest/email-attachment", response_model=InvoiceOut)
    async def ingest_email_attachment(
        email_message_id: str = Form(...),
        sender: str = Form(""),
        subject: str = Form(""),
        attachment: UploadFile = File(...),
        db: Session = Depends(get_db),
    ):
        data = await attachment.read()
        inv = crud.create_invoice_from_attachment(
            db=db,
            email_message_id=email_message_id,
            sender=sender,
            subject=subject,
            filename=attachment.filename or "attachment",
            content_type=attachment.content_type or "application/octet-stream",
            file_bytes=data,
        )
        return inv

    @app.get("/invoices/{invoice_id}", response_model=InvoiceOut)
    def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
        try:
            invoice_uuid = uuid.UUID(invoice_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid invoice ID format")
        
        inv = db.get(Invoice, invoice_uuid)
        if inv is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return inv

# ---- MVP background worker loop (polling) ----
def worker_loop():
    while True:
        db = SessionLocal()
        try:
            # Process OCR jobs first
            ocr_job = pick_next_ocr_job(db)
            if ocr_job:
                try:
                    # Mark pending (prevents double-processing if multiple workers)
                    mark_ocr_pending(db, ocr_job)

                    # TODO: STEP 3 OCR will happen here.
                    # For now, simulate OCR with sample text:
                    sample_ocr_text = (
                        "INVOICE\n"
                        "Invoice No: INV-2024-001\n"
                        "Date: 2024-12-15\n"
                        "From: Acme Corporation\n\n"
                        "Subtotal: $1,000.00\n"
                        "Tax: $100.00\n"
                        "Total: $1,100.00\n"
                        "Currency: USD"
                    )
                    time.sleep(0.2)
                    mark_ocr_done(db, ocr_job, ocr_text=sample_ocr_text)
                except Exception as e:
                    # if we have a job object in scope, schedule retry
                    mark_retry(db, ocr_job, error=str(e))
                finally:
                    db.close()
                    continue

            # Process extraction jobs
            extraction_job = pick_next_extraction_job(db)
            if extraction_job:
                try:
                    from app.extraction.rule_based import extract_invoice_fields
                    
                    # Extract fields from OCR text
                    extracted_fields = extract_invoice_fields(extraction_job.ocr_text or "")
                    
                    # Mark as extracted (even if some fields are None, that's OK)
                    mark_extracted(db, extraction_job, extracted_fields)
                    
                except Exception as e:
                    # Log error but don't crash - mark as failed
                    error_msg = f"Extraction failed: {str(e)}"
                    mark_extraction_failed(db, extraction_job, error_msg)
                finally:
                    db.close()
                    continue

            # No jobs available, sleep
            db.close()
            time.sleep(2)

        except Exception as e:
            # Unexpected error - log and continue
            print(f"Worker error: {e}")
            db.close()
            time.sleep(2)

@app.on_event("startup")
def start_worker():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

