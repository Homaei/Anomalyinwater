from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import structlog
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import time
from typing import List, Optional
import hashlib
import os
from PIL import Image
import io

from app.database import get_db, engine
from app import models, schemas, crud, storage, queue, auth_client
from app.config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WWTP Upload Service",
    description="Image upload and processing service for WWTP Anomaly Detection",
    version="1.0.0"
)

logger = structlog.get_logger()

# Prometheus metrics
UPLOAD_COUNT = Counter('uploads_total', 'Total uploads', ['status'])
UPLOAD_DURATION = Histogram('upload_duration_seconds', 'Upload processing duration')
FILE_SIZE_HISTOGRAM = Histogram('upload_file_size_bytes', 'Upload file sizes')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    if request.url.path.startswith("/upload"):
        UPLOAD_DURATION.observe(duration)
    
    return response

@app.get("/")
async def root():
    return {"message": "WWTP Upload Service", "version": "1.0.0"}

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        storage.check_connection()
        queue.check_connection()
        return {"status": "healthy", "database": "connected", "storage": "connected", "queue": "connected"}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

async def validate_image(file: UploadFile) -> tuple[bool, str]:
    """Validate uploaded file is a valid image"""
    try:
        # Check file type
        if not file.content_type.startswith('image/'):
            return False, "File must be an image"
        
        # Check file size (max 50MB)
        contents = await file.read()
        if len(contents) > 50 * 1024 * 1024:
            return False, "File size must be less than 50MB"
        
        # Reset file pointer
        await file.seek(0)
        
        # Try to open with PIL to validate it's a real image
        try:
            image = Image.open(io.BytesIO(contents))
            image.verify()
            await file.seek(0)  # Reset again
            return True, ""
        except Exception:
            return False, "Invalid image file"
    except Exception as e:
        logger.error("Error validating image", error=str(e))
        return False, "Error validating image"

def calculate_file_hash(contents: bytes) -> str:
    """Calculate SHA-256 hash of file contents"""
    return hashlib.sha256(contents).hexdigest()

def extract_image_metadata(contents: bytes) -> dict:
    """Extract metadata from image"""
    try:
        image = Image.open(io.BytesIO(contents))
        return {
            "width": image.width,
            "height": image.height,
            "format": image.format,
            "mode": image.mode,
            "has_transparency": image.mode in ('RGBA', 'LA'),
            "exif": dict(image.getexif()) if hasattr(image, 'getexif') else {}
        }
    except Exception as e:
        logger.warning("Could not extract image metadata", error=str(e))
        return {}

@app.post("/upload", response_model=schemas.ImageUploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    start_time = time.time()
    
    try:
        # Validate image
        is_valid, error_msg = await validate_image(file)
        if not is_valid:
            UPLOAD_COUNT.labels(status="invalid").inc()
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Read file contents
        contents = await file.read()
        file_size = len(contents)
        FILE_SIZE_HISTOGRAM.observe(file_size)
        
        # Calculate hash for deduplication
        file_hash = calculate_file_hash(contents)
        
        # Check for duplicate
        existing_image = crud.get_image_by_hash(db, file_hash)
        if existing_image:
            UPLOAD_COUNT.labels(status="duplicate").inc()
            return schemas.ImageUploadResponse(
                id=existing_image.id,
                filename=existing_image.filename,
                message="File already exists",
                duplicate=True
            )
        
        # Extract image metadata
        metadata = extract_image_metadata(contents)
        
        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1].lower()
        unique_filename = f"{file_hash[:16]}_{int(time.time())}{file_extension}"
        
        # Store file in MinIO
        file_path = await storage.store_file(unique_filename, contents, file.content_type)
        
        # Create database record
        image_data = schemas.ImageCreate(
            filename=unique_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type,
            width=metadata.get("width"),
            height=metadata.get("height"),
            uploaded_by=current_user["user_id"],
            metadata=metadata,
            checksum=file_hash
        )
        
        db_image = crud.create_image(db, image_data)
        
        # Queue for ML processing
        queue_message = {
            "image_id": str(db_image.id),
            "file_path": file_path,
            "uploaded_by": current_user["user_id"],
            "timestamp": time.time()
        }
        
        await queue.send_to_ml_queue(queue_message)
        
        UPLOAD_COUNT.labels(status="success").inc()
        
        logger.info(
            "Image uploaded successfully",
            image_id=str(db_image.id),
            filename=unique_filename,
            file_size=file_size,
            user_id=current_user["user_id"]
        )
        
        return schemas.ImageUploadResponse(
            id=db_image.id,
            filename=unique_filename,
            message="Upload successful",
            duplicate=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        UPLOAD_COUNT.labels(status="error").inc()
        logger.error("Upload failed", error=str(e))
        raise HTTPException(status_code=500, detail="Upload failed")
    finally:
        duration = time.time() - start_time
        UPLOAD_DURATION.observe(duration)

@app.post("/upload/batch", response_model=List[schemas.ImageUploadResponse])
async def upload_multiple_images(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
    
    results = []
    for file in files:
        try:
            # Reset file pointer for each processing
            await file.seek(0)
            result = await upload_image(file, current_user, db)
            results.append(result)
        except HTTPException as e:
            results.append(schemas.ImageUploadResponse(
                id=None,
                filename=file.filename,
                message=e.detail,
                duplicate=False,
                error=True
            ))
        except Exception as e:
            logger.error("Batch upload error", filename=file.filename, error=str(e))
            results.append(schemas.ImageUploadResponse(
                id=None,
                filename=file.filename,
                message="Upload failed",
                duplicate=False,
                error=True
            ))
    
    return results

@app.get("/images", response_model=List[schemas.Image])
async def list_images(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    # Users can only see their own images unless they're admin/reviewer
    if current_user["role"] in ["admin", "reviewer"]:
        images = crud.get_images(db, skip=skip, limit=limit, status_filter=status_filter)
    else:
        images = crud.get_images_by_user(db, current_user["user_id"], skip=skip, limit=limit, status_filter=status_filter)
    
    return images

@app.get("/images/{image_id}", response_model=schemas.Image)
async def get_image(
    image_id: str,
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    image = crud.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check permissions
    if current_user["role"] not in ["admin", "reviewer"] and str(image.uploaded_by) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this image")
    
    return image

@app.delete("/images/{image_id}")
async def delete_image(
    image_id: str,
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    image = crud.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Check permissions - only owner or admin can delete
    if current_user["role"] != "admin" and str(image.uploaded_by) != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this image")
    
    # Delete from storage
    await storage.delete_file(image.file_path)
    
    # Delete from database
    crud.delete_image(db, image_id)
    
    logger.info("Image deleted", image_id=image_id, deleted_by=current_user["user_id"])
    
    return {"message": "Image deleted successfully"}

@app.get("/stats")
async def get_upload_stats(
    current_user: dict = Depends(auth_client.get_current_user),
    db: Session = Depends(get_db)
):
    if current_user["role"] in ["admin", "reviewer"]:
        stats = crud.get_upload_stats(db)
    else:
        stats = crud.get_user_upload_stats(db, current_user["user_id"])
    
    return stats