from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app import models, schemas
import uuid
from datetime import datetime, date
from typing import List, Optional

def create_image(db: Session, image: schemas.ImageCreate):
    db_image = models.Image(
        filename=image.filename,
        original_filename=image.original_filename,
        file_path=image.file_path,
        file_size=image.file_size,
        mime_type=image.mime_type,
        width=image.width,
        height=image.height,
        uploaded_by=uuid.UUID(image.uploaded_by),
        metadata=image.metadata,
        checksum=image.checksum
    )
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image

def get_image(db: Session, image_id: str):
    return db.query(models.Image).filter(models.Image.id == uuid.UUID(image_id)).first()

def get_image_by_hash(db: Session, checksum: str):
    return db.query(models.Image).filter(models.Image.checksum == checksum).first()

def get_images(db: Session, skip: int = 0, limit: int = 100, status_filter: Optional[str] = None):
    query = db.query(models.Image)
    if status_filter:
        query = query.filter(models.Image.processing_status == status_filter)
    return query.order_by(models.Image.upload_timestamp.desc()).offset(skip).limit(limit).all()

def get_images_by_user(db: Session, user_id: str, skip: int = 0, limit: int = 100, status_filter: Optional[str] = None):
    query = db.query(models.Image).filter(models.Image.uploaded_by == uuid.UUID(user_id))
    if status_filter:
        query = query.filter(models.Image.processing_status == status_filter)
    return query.order_by(models.Image.upload_timestamp.desc()).offset(skip).limit(limit).all()

def update_image_status(db: Session, image_id: str, status: str):
    db_image = get_image(db, image_id)
    if db_image:
        db_image.processing_status = status
        db.commit()
        db.refresh(db_image)
    return db_image

def delete_image(db: Session, image_id: str):
    db_image = get_image(db, image_id)
    if db_image:
        db.delete(db_image)
        db.commit()
    return db_image

def get_upload_stats(db: Session):
    total_uploads = db.query(func.count(models.Image.id)).scalar()
    total_size = db.query(func.sum(models.Image.file_size)).scalar() or 0
    
    today = date.today()
    uploads_today = db.query(func.count(models.Image.id)).filter(
        func.date(models.Image.upload_timestamp) == today
    ).scalar()
    
    pending_processing = db.query(func.count(models.Image.id)).filter(
        models.Image.processing_status == "pending"
    ).scalar()
    
    completed_processing = db.query(func.count(models.Image.id)).filter(
        models.Image.processing_status == "completed"
    ).scalar()
    
    failed_processing = db.query(func.count(models.Image.id)).filter(
        models.Image.processing_status == "failed"
    ).scalar()
    
    return schemas.UploadStats(
        total_uploads=total_uploads,
        total_size=total_size,
        uploads_today=uploads_today,
        pending_processing=pending_processing,
        completed_processing=completed_processing,
        failed_processing=failed_processing
    )

def get_user_upload_stats(db: Session, user_id: str):
    user_uuid = uuid.UUID(user_id)
    
    total_uploads = db.query(func.count(models.Image.id)).filter(
        models.Image.uploaded_by == user_uuid
    ).scalar()
    
    total_size = db.query(func.sum(models.Image.file_size)).filter(
        models.Image.uploaded_by == user_uuid
    ).scalar() or 0
    
    today = date.today()
    uploads_today = db.query(func.count(models.Image.id)).filter(
        and_(
            models.Image.uploaded_by == user_uuid,
            func.date(models.Image.upload_timestamp) == today
        )
    ).scalar()
    
    pending_processing = db.query(func.count(models.Image.id)).filter(
        and_(
            models.Image.uploaded_by == user_uuid,
            models.Image.processing_status == "pending"
        )
    ).scalar()
    
    completed_processing = db.query(func.count(models.Image.id)).filter(
        and_(
            models.Image.uploaded_by == user_uuid,
            models.Image.processing_status == "completed"
        )
    ).scalar()
    
    failed_processing = db.query(func.count(models.Image.id)).filter(
        and_(
            models.Image.uploaded_by == user_uuid,
            models.Image.processing_status == "failed"
        )
    ).scalar()
    
    return schemas.UploadStats(
        total_uploads=total_uploads,
        total_size=total_size,
        uploads_today=uploads_today,
        pending_processing=pending_processing,
        completed_processing=completed_processing,
        failed_processing=failed_processing
    )