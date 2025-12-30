from datetime import datetime
from pydantic import BaseModel
from typing import Optional
import uuid
from app.models import InvoiceStatus

class InvoiceOut(BaseModel):
    id: uuid.UUID
    email_message_id: str
    sender: str
    subject: str
    filename: str
    sha256: str
    storage_path: str
    status: InvoiceStatus
    attempt_count: int
    next_attempt_at: datetime
    last_error: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

