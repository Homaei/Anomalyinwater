from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HumanVerdict(str, Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    TRUE_NEGATIVE = "true_negative"
    FALSE_NEGATIVE = "false_negative"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(str, Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    OPERATOR = "operator"


# Base schemas
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = UserRole.OPERATOR
    is_active: bool = True


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None


class ImageBase(BaseModel):
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)
    checksum: str


class Image(ImageBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    uploaded_by: UUID
    upload_timestamp: datetime


class DetectionBase(BaseModel):
    model_version: str
    confidence_score: float = Field(..., ge=0, le=1)
    is_anomaly: bool
    anomaly_type: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    processing_time_ms: Optional[int] = None


class Detection(DetectionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    image_id: UUID
    detected_at: datetime


class ReviewBase(BaseModel):
    review_status: ReviewStatus = ReviewStatus.PENDING
    human_verdict: Optional[HumanVerdict] = None
    confidence_level: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None
    review_duration_seconds: Optional[int] = None


class ReviewCreate(ReviewBase):
    detection_id: UUID


class ReviewUpdate(BaseModel):
    review_status: Optional[ReviewStatus] = None
    human_verdict: Optional[HumanVerdict] = None
    confidence_level: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None
    review_duration_seconds: Optional[int] = None


class Review(ReviewBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    detection_id: UUID
    reviewer_id: UUID
    reviewed_at: datetime


class ReviewWithDetails(Review):
    detection: Detection
    image: Image
    reviewer: User


class DetectionWithReview(Detection):
    image: Image
    reviews: List[Review] = []


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int


class ReviewStats(BaseModel):
    total_pending: int
    total_approved: int
    total_rejected: int
    avg_review_time: Optional[float]
    reviewer_stats: Dict[str, Dict[str, int]]


class AnomalyStats(BaseModel):
    total_detections: int
    anomaly_count: int
    avg_confidence: float
    true_positive_rate: Optional[float]
    false_positive_rate: Optional[float]


class WebSocketMessage(BaseModel):
    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class NotificationMessage(BaseModel):
    user_id: Optional[UUID] = None
    message: str
    severity: str = "info"  # info, warning, error
    data: Dict[str, Any] = Field(default_factory=dict)


# Health check schema
class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
    version: str
    dependencies: Dict[str, str]


# Error schemas
class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)