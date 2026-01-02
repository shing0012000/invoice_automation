from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import threading
import time
import asyncio
import uuid
import os
import logging

from app.db import Base, engine, get_db, SessionLocal
from app.schemas import InvoiceOut
from app import crud
from app.models import Invoice, InvoiceStatus
from app.config import settings
from app.worker import (
    pick_next_ocr_job, mark_ocr_pending, mark_ocr_done, mark_retry,
    pick_next_extraction_job, mark_extracted, mark_extraction_failed
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure FastAPI based on demo mode
if settings.demo_mode:
    app = FastAPI(title="Invoice Automation Demo", docs_url=None, redoc_url=None)
else:
    app = FastAPI(title="Invoice Automation MVP")

# Startup self-checks and schema creation
@app.on_event("startup")
async def startup_checks():
    """Perform startup validation and logging."""
    logger.info("=" * 60)
    logger.info("Invoice Automation - Startup Checks")
    logger.info("=" * 60)
    
    # Log database configuration
    db_dialect = engine.dialect.name
    logger.info(f"Database dialect: {db_dialect}")
    logger.info(f"Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    
    # Log demo mode status
    logger.info(f"Demo mode: {settings.demo_mode}")
    if settings.demo_mode:
        logger.info("  - Swagger UI: DISABLED")
        logger.info("  - Internal endpoints: HIDDEN")
    else:
        logger.info("  - Swagger UI: ENABLED at /docs")
        logger.info("  - Internal endpoints: AVAILABLE")
    
    # Log storage configuration
    storage_abs = os.path.abspath(settings.storage_dir)
    logger.info(f"Storage directory: {storage_abs}")
    try:
        os.makedirs(settings.storage_dir, exist_ok=True)
        logger.info(f"  - Directory exists/created: OK")
    except Exception as e:
        logger.warning(f"  - Directory creation failed (non-fatal): {e}")
    
    # Create schema (fast operation)
    try:
        logger.info("Creating database schema...")
        Base.metadata.create_all(bind=engine)
        logger.info("  - Schema creation: SUCCESS")
        
        # Migrate: Add confidence_status column if it doesn't exist (for existing databases)
        try:
            from sqlalchemy import inspect, text
            inspector = inspect(engine)
            
            # Check if invoices table exists
            if 'invoices' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('invoices')]
                
                if 'confidence_status' not in columns:
                    logger.info("  - Adding confidence_status column (migration)...")
                    if engine.dialect.name == 'sqlite':
                        # SQLite: ALTER TABLE to add column (SQLite stores enum as VARCHAR)
                        with engine.connect() as conn:
                            conn.execute(text("ALTER TABLE invoices ADD COLUMN confidence_status VARCHAR(20) DEFAULT 'ERROR'"))
                            conn.commit()
                        logger.info("  - Migration: confidence_status column added to SQLite database")
                    else:
                        # PostgreSQL: ALTER TABLE to add column
                        with engine.connect() as conn:
                            conn.execute(text("ALTER TABLE invoices ADD COLUMN confidence_status VARCHAR(20) DEFAULT 'ERROR'"))
                            conn.commit()
                        logger.info("  - Migration: confidence_status column added to PostgreSQL database")
                else:
                    logger.debug("  - confidence_status column already exists")
            else:
                logger.debug("  - invoices table doesn't exist yet (will be created)")
        except Exception as migration_error:
            logger.warning(f"  - Migration check failed (non-fatal): {migration_error}")
            # Continue - schema creation succeeded
    except Exception as e:
        logger.error(f"  - Schema creation failed: {e}")
        # Don't block startup - health check will catch this
    
    logger.info("=" * 60)
    logger.info("Startup checks complete. Application ready.")
    logger.info("=" * 60)

# Create tables on module load (fallback if startup event doesn't fire)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning(f"Schema creation on module load failed (may be expected): {e}")

# Health check endpoint (required for cloud platforms)
@app.get("/health")
async def health_check():
    """
    Health check endpoint for cloud platform monitoring.
    This endpoint must respond quickly to prevent deployment timeouts.
    """
    try:
        # Quick database connectivity check
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.warning(f"Health check: database connection failed: {e}")
        db_status = "disconnected"
    
    return {
        "status": "healthy",
        "service": "invoice-automation",
        "database": db_status,
        "demo_mode": settings.demo_mode
    }

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
        max_wait = 60  # seconds (increased for PDF processing)
        wait_interval = 0.5
        waited = 0
        
        while waited < max_wait:
            db.refresh(inv)
            if inv.status == InvoiceStatus.OCR_DONE:
                break
            elif inv.status == InvoiceStatus.FAILED_RETRYABLE or inv.status == InvoiceStatus.FAILED_FINAL:
                # Extraction failed - return error immediately
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
                "extracted_fields": inv.extracted_fields,
                "confidence_status": inv.confidence_status.value if inv.confidence_status else "ERROR"
            }
        elif inv.status == InvoiceStatus.EXTRACTION_FAILED:
            error_msg = inv.last_error or "Field extraction failed"
            # Provide user-friendly error message
            if "PDF text extraction failed" in error_msg or "image-based" in error_msg.lower():
                error_msg = "PDF appears to be image-based (scanned). This app requires text-based PDFs. Please use a PDF with selectable text."
            return {
                "status": "extraction_failed",
                "error": error_msg,
                "extracted_fields": inv.extracted_fields or {}
            }
        elif inv.status in [InvoiceStatus.FAILED_RETRYABLE, InvoiceStatus.FAILED_FINAL]:
            error_msg = inv.last_error or "Processing failed"
            if "PDF text extraction failed" in error_msg or "image-based" in error_msg.lower():
                error_msg = "PDF appears to be image-based (scanned). This app requires text-based PDFs. Please use a PDF with selectable text."
            return {
                "status": "error",
                "error": error_msg,
                "extracted_fields": {}
            }
        else:
            return {
                "status": "timeout",
                "error": "Processing timed out. The PDF may be too large or complex. Please try again with a simpler PDF.",
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
        # Validate UUID format (but store as string)
        try:
            uuid.UUID(invoice_id)  # Validate format
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid invoice ID format")
        
        # Query using string ID (portable across databases)
        inv = db.get(Invoice, invoice_id)
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

                    # Extract text from file (PDF or image)
                    from app.text_extraction import extract_text_from_file, is_supported_file_type
                    
                    ocr_text = None
                    # Resolve path (handle both relative and absolute)
                    file_path = ocr_job.storage_path
                    if file_path:
                        # Try absolute path first, then relative
                        if not os.path.isabs(file_path):
                            file_path = os.path.abspath(file_path)
                        
                        logger.info(f"Extracting text from file: {file_path}")
                        logger.info(f"  - Path exists: {os.path.exists(file_path)}")
                        logger.info(f"  - Content type: {ocr_job.content_type}")
                        logger.info(f"  - Filename: {ocr_job.filename}")
                        
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)
                            logger.info(f"  - File size: {file_size} bytes")
                            
                            # Check if file type is supported
                            if not is_supported_file_type(file_path, ocr_job.content_type):
                                error_msg = f"Unsupported file type: {ocr_job.content_type or 'unknown'}. Supported: PDF, PNG, JPEG, TIFF"
                                logger.warning(f"Invoice {ocr_job.id}: {error_msg}")
                                mark_retry(db, ocr_job, error=error_msg)
                                db.close()
                                continue
                        
                        if os.path.exists(file_path):
                            # Use unified extraction (handles both PDF and images)
                            ocr_text = extract_text_from_file(file_path, ocr_job.content_type)
                        else:
                            logger.error(f"  - File not found at: {file_path}")
                            logger.error(f"  - Current working directory: {os.getcwd()}")
                            logger.error(f"  - Storage dir: {os.path.abspath(settings.storage_dir)}")
                        
                        if not ocr_text:
                            # If extraction fails, mark as retryable error
                            error_msg = "Text extraction failed - file may be corrupted or unsupported format"
                            logger.warning(f"Invoice {ocr_job.id}: {error_msg}")
                            # Log additional diagnostics
                            logger.warning(f"  - File path: {file_path}")
                            logger.warning(f"  - File exists: {os.path.exists(file_path) if file_path else False}")
                            if file_path and os.path.exists(file_path):
                                logger.warning(f"  - File size: {os.path.getsize(file_path)} bytes")
                            mark_retry(db, ocr_job, error=error_msg)
                            db.close()
                            continue
                    else:
                        error_msg = f"File not found: {ocr_job.storage_path}"
                        logger.error(f"Invoice {ocr_job.id}: {error_msg}")
                        logger.error(f"  - Current working directory: {os.getcwd()}")
                        logger.error(f"  - Storage dir: {os.path.abspath(settings.storage_dir)}")
                        mark_retry(db, ocr_job, error=error_msg)
                        db.close()
                        continue
                    
                    # Mark OCR as done with extracted text
                    mark_ocr_done(db, ocr_job, ocr_text=ocr_text)
                    logger.info(f"Invoice {ocr_job.id}: Text extraction complete ({len(ocr_text)} characters)")
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
                    from app.extraction.pipeline import extract_invoice_fields_multi_level, get_extraction_level_config
                    
                    # Get extraction level configuration
                    level_config = get_extraction_level_config()
                    
                    # Resolve absolute path for file (PDF or image)
                    file_path = os.path.abspath(extraction_job.storage_path) if extraction_job.storage_path else None
                    
                    # Extract fields using multi-level pipeline with smart LLM fallback
                    # Level 1 (OCR) already done - ocr_text available
                    # Level 1.5 (Rule-based): Always runs first (free, fast)
                    # Level 2 (Structural): Enabled by default (works best with PDFs)
                    # Level 3 (Semantic/LLM): Smart fallback - only used when needed (cost optimization)
                    extracted_fields, confidence_status = extract_invoice_fields_multi_level(
                        file_path=file_path,
                        ocr_text=extraction_job.ocr_text or "",
                        enable_level_2=level_config["enable_level_2"],
                        enable_level_3=level_config["enable_level_3"],
                        use_llm_fallback=level_config.get("use_llm_fallback", True),
                        min_extraction_rate=level_config.get("min_extraction_rate", 0.5)
                    )
                    
                    # Mark as extracted with confidence status (even if some fields are None, that's OK)
                    mark_extracted(db, extraction_job, extracted_fields, confidence_status)
                    logger.info(f"Invoice {extraction_job.id}: Multi-level extraction complete. Confidence: {confidence_status.value}")
                    
                except Exception as e:
                    # Log error but don't crash - mark as failed
                    error_msg = f"Extraction failed: {str(e)}"
                    logger.error(f"Invoice {extraction_job.id}: {error_msg}", exc_info=True)
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
    """Start background worker thread."""
    logger.info("Starting background worker thread...")
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    logger.info("Background worker started.")

