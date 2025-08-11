from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class ImageBase(BaseModel):
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None

class ImageCreate(ImageBase):
    uploaded_by: str
    metadata: Dict[str, Any] = {}
    checksum: str

class Image(ImageBase):
    id: uuid.UUID
    uploaded_by: uuid.UUID
    upload_timestamp: datetime
    processing_status: str
    metadata: Dict[str, Any]
    checksum: str

    class Config:
        from_attributes = True

class ImageUploadResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    filename: str
    message: str
    duplicate: bool = False
    error: bool = False

class UploadStats(BaseModel):
    total_uploads: int
    total_size: int
    uploads_today: int
    pending_processing: int
    completed_processing: int
    failed_processing: int