from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from app.config import settings
from app.database import get_db, init_db
from app.auth_client import get_current_user, require_permission
from app.crud import review_crud, detection_crud
from app.schemas import (
    Review, ReviewCreate, ReviewUpdate, ReviewWithDetails, 
    DetectionWithReview, PaginatedResponse, ReviewStats, 
    AnomalyStats, HealthCheck, ErrorResponse, User
)
from app.websocket_manager import manager, notification_service, periodic_cleanup
from app.metrics import metrics, get_metrics
from app.models import Review as ReviewModel, Detection as DetectionModel
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting Review Service", version=settings.api_version)
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise
    
    # Start background tasks
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    # Update system health
    metrics.update_system_health(True)
    
    yield
    
    # Shutdown
    logger.info("Shutting down Review Service")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    metrics.update_system_health(False)


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan
)

# Security
security = HTTPBearer()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure appropriately for production
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect HTTP metrics"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Record metrics
    metrics.record_http_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    return response


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware for request logging"""
    start_time = time.time()
    
    # Log request
    logger.info(
        "HTTP request started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host
    )
    
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log response
    logger.info(
        "HTTP request completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    return response


# Authentication dependency
async def get_current_authenticated_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.split(" ")[1]
    user = await get_current_user(token)
    
    # Record auth metrics
    metrics.record_auth_request("success")
    
    return user


# Health check endpoint
@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    return HealthCheck(
        status="healthy",
        timestamp=time.time(),
        version=settings.api_version,
        dependencies={
            "database": "connected",
            "websocket": "active",
            "auth_service": "available"
        }
    )


# Metrics endpoint
@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(
        content=get_metrics(),
        media_type="text/plain"
    )


# Review endpoints
@app.get("/reviews", response_model=PaginatedResponse)
async def get_reviews(
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
    reviewer_id: Optional[UUID] = None,
    sort_by: str = "reviewed_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get paginated reviews"""
    await require_permission(current_user, "read")
    
    # Validate page size
    if size > settings.max_page_size:
        size = settings.max_page_size
    
    skip = (page - 1) * size
    
    reviews, total = review_crud.get_reviews(
        db, 
        skip=skip, 
        limit=size,
        status=status,
        reviewer_id=reviewer_id,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    pages = (total + size - 1) // size
    
    return PaginatedResponse(
        items=reviews,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@app.get("/reviews/{review_id}", response_model=ReviewWithDetails)
async def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get specific review with details"""
    await require_permission(current_user, "read")
    
    review = review_crud.get_review_with_details(db, review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    return review


@app.post("/reviews", response_model=Review, status_code=status.HTTP_201_CREATED)
async def create_review(
    review: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Create new review"""
    await require_permission(current_user, "review")
    
    # Check if detection exists
    detection = detection_crud.get_detection(db, review.detection_id)
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found"
        )
    
    # Create review
    db_review = review_crud.create_review(db, review, current_user.id)
    
    # Record metrics
    metrics.record_review_processed("created")
    
    # Send WebSocket notification
    await notification_service.notify_new_detection(
        detection.id, 
        detection.is_anomaly, 
        detection.confidence_score
    )
    
    logger.info(
        "Review created",
        review_id=str(db_review.id),
        detection_id=str(review.detection_id),
        reviewer_id=str(current_user.id)
    )
    
    return db_review


@app.put("/reviews/{review_id}", response_model=Review)
async def update_review(
    review_id: UUID,
    review_update: ReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Update existing review"""
    await require_permission(current_user, "update_review")
    
    # Get existing review
    existing_review = review_crud.get_review(db, review_id)
    if not existing_review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check permission (reviewers can only update their own reviews)
    if current_user.role != "admin" and existing_review.reviewer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only update your own reviews"
        )
    
    # Update review
    updated_review = review_crud.update_review(db, review_id, review_update)
    
    # Record metrics
    metrics.record_review_processed(
        updated_review.review_status,
        updated_review.human_verdict,
        updated_review.review_duration_seconds
    )
    
    # Send WebSocket notification
    if updated_review.review_status in ["approved", "rejected"]:
        await notification_service.notify_review_completed(
            updated_review.id,
            updated_review.detection_id,
            updated_review.human_verdict or "unknown"
        )
    
    logger.info(
        "Review updated",
        review_id=str(review_id),
        status=updated_review.review_status,
        verdict=updated_review.human_verdict,
        reviewer_id=str(current_user.id)
    )
    
    return updated_review


@app.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Delete review"""
    await require_permission(current_user, "delete")
    
    # Check if review exists
    existing_review = review_crud.get_review(db, review_id)
    if not existing_review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Delete review
    success = review_crud.delete_review(db, review_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete review"
        )
    
    logger.info("Review deleted", review_id=str(review_id), user_id=str(current_user.id))


@app.get("/reviews/pending", response_model=List[ReviewWithDetails])
async def get_pending_reviews(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get pending reviews for assignment"""
    await require_permission(current_user, "read")
    
    reviews = review_crud.get_pending_reviews(db, limit)
    return reviews


@app.post("/reviews/assign/{detection_id}", response_model=Review)
async def assign_review(
    detection_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Assign detection for review"""
    await require_permission(current_user, "review")
    
    review = review_crud.assign_review(db, detection_id, current_user.id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to assign review"
        )
    
    logger.info(
        "Review assigned",
        review_id=str(review.id),
        detection_id=str(detection_id),
        reviewer_id=str(current_user.id)
    )
    
    return review


# Detection endpoints
@app.get("/detections", response_model=PaginatedResponse)
async def get_detections_for_review(
    page: int = 1,
    size: int = 20,
    is_anomaly: Optional[bool] = None,
    min_confidence: Optional[float] = None,
    unreviewed_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get detections for review"""
    await require_permission(current_user, "read")
    
    # Validate page size
    if size > settings.max_page_size:
        size = settings.max_page_size
    
    skip = (page - 1) * size
    
    detections, total = detection_crud.get_detections_for_review(
        db,
        skip=skip,
        limit=size,
        is_anomaly=is_anomaly,
        min_confidence=min_confidence,
        unreviewed_only=unreviewed_only
    )
    
    pages = (total + size - 1) // size
    
    return PaginatedResponse(
        items=detections,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@app.get("/detections/{detection_id}", response_model=DetectionWithReview)
async def get_detection(
    detection_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get specific detection with reviews"""
    await require_permission(current_user, "read")
    
    detection = detection_crud.get_detection(db, detection_id)
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found"
        )
    
    return detection


# Statistics endpoints
@app.get("/stats/reviews", response_model=ReviewStats)
async def get_review_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get review statistics"""
    await require_permission(current_user, "read")
    
    stats = review_crud.get_review_stats(db, days)
    return ReviewStats(**stats)


@app.get("/stats/workload/{reviewer_id}")
async def get_reviewer_workload(
    reviewer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get reviewer workload"""
    await require_permission(current_user, "read")
    
    workload = review_crud.get_reviewer_workload(db, reviewer_id)
    return workload


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None
):
    """WebSocket endpoint for real-time notifications"""
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    
    # Authenticate user
    try:
        user = await get_current_user(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception as e:
        logger.error("WebSocket authentication failed", error=str(e))
        await websocket.close(code=4001, reason="Authentication failed")
        return
    
    # Connect user
    await manager.connect(websocket, user)
    
    try:
        # Update connection metrics
        connected_users = manager.get_connected_users()
        metrics.record_websocket_connection(len(connected_users))
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "heartbeat":
                    await manager.handle_heartbeat(websocket)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("WebSocket message error", error=str(e))
                break
    
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        
        # Update connection metrics
        connected_users = manager.get_connected_users()
        metrics.record_websocket_connection(len(connected_users))


@app.get("/ws/connected")
async def get_connected_users(
    current_user: User = Depends(get_current_authenticated_user)
):
    """Get currently connected WebSocket users"""
    await require_permission(current_user, "read")
    
    connected_users = manager.get_connected_users()
    return {"connected_users": connected_users, "total": len(connected_users)}


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        method=request.method
    )
    
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )