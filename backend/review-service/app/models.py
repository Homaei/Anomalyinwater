from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(20), default='operator')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))

    # Relationships
    uploaded_images = relationship("Image", back_populates="uploader")
    reviews = relationship("Review", back_populates="reviewer")

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'reviewer', 'operator')", name='check_user_role'),
    )


class Image(Base):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    processing_status = Column(String(20), default='pending')
    metadata = Column(JSONB, default={})
    checksum = Column(String(64), nullable=False)

    # Relationships
    uploader = relationship("User", back_populates="uploaded_images")
    detections = relationship("Detection", back_populates="image", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("processing_status IN ('pending', 'processing', 'completed', 'failed')", 
                       name='check_image_processing_status'),
    )


class Detection(Base):
    __tablename__ = "detections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    model_version = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, nullable=False)
    anomaly_type = Column(String(100))
    bounding_box = Column(JSONB)  # {x, y, width, height}
    features = Column(JSONB, default={})
    processing_time_ms = Column(Integer)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    image = relationship("Image", back_populates="detections")
    reviews = relationship("Review", back_populates="detection", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", 
                       name='check_detection_confidence_score'),
    )


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    detection_id = Column(UUID(as_uuid=True), ForeignKey("detections.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    review_status = Column(String(20), default='pending')
    human_verdict = Column(String(20))
    confidence_level = Column(Integer)
    notes = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now())
    review_duration_seconds = Column(Integer)

    # Relationships
    detection = relationship("Detection", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")

    __table_args__ = (
        CheckConstraint("review_status IN ('pending', 'approved', 'rejected')", 
                       name='check_review_status'),
        CheckConstraint("human_verdict IN ('true_positive', 'false_positive', 'true_negative', 'false_negative')", 
                       name='check_human_verdict'),
        CheckConstraint("confidence_level >= 1 AND confidence_level <= 5", 
                       name='check_confidence_level'),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    details = Column(JSONB, default={})
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])


class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    metric_type = Column(String(20), nullable=False)
    labels = Column(JSONB, default={})
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("metric_type IN ('counter', 'gauge', 'histogram')", 
                       name='check_metric_type'),
    )