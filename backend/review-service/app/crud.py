from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc, func, and_, or_
from app.models import Review, Detection, Image, User
from app.schemas import ReviewCreate, ReviewUpdate, ReviewStatus, HumanVerdict
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ReviewCRUD:
    def get_review(self, db: Session, review_id: UUID) -> Optional[Review]:
        """Get single review by ID"""
        return db.query(Review).filter(Review.id == review_id).first()
    
    def get_review_with_details(self, db: Session, review_id: UUID) -> Optional[Review]:
        """Get review with detection, image, and reviewer details"""
        return (
            db.query(Review)
            .options(
                joinedload(Review.detection).joinedload(Detection.image),
                joinedload(Review.reviewer)
            )
            .filter(Review.id == review_id)
            .first()
        )
    
    def get_reviews(
        self, 
        db: Session,
        skip: int = 0,
        limit: int = 20,
        status: Optional[ReviewStatus] = None,
        reviewer_id: Optional[UUID] = None,
        sort_by: str = "reviewed_at",
        sort_order: str = "desc"
    ) -> Tuple[List[Review], int]:
        """Get paginated reviews with filters"""
        query = db.query(Review).options(
            joinedload(Review.detection).joinedload(Detection.image),
            joinedload(Review.reviewer)
        )
        
        # Apply filters
        if status:
            query = query.filter(Review.review_status == status)
        
        if reviewer_id:
            query = query.filter(Review.reviewer_id == reviewer_id)
        
        # Apply sorting
        sort_column = getattr(Review, sort_by, Review.reviewed_at)
        if sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        reviews = query.offset(skip).limit(limit).all()
        
        return reviews, total
    
    def get_pending_reviews(self, db: Session, limit: int = 50) -> List[Review]:
        """Get pending reviews for assignment"""
        return (
            db.query(Review)
            .options(
                joinedload(Review.detection).joinedload(Detection.image),
                joinedload(Review.reviewer)
            )
            .filter(Review.review_status == ReviewStatus.PENDING)
            .order_by(Review.reviewed_at)
            .limit(limit)
            .all()
        )
    
    def create_review(self, db: Session, review: ReviewCreate, reviewer_id: UUID) -> Review:
        """Create a new review"""
        db_review = Review(
            detection_id=review.detection_id,
            reviewer_id=reviewer_id,
            review_status=review.review_status,
            human_verdict=review.human_verdict,
            confidence_level=review.confidence_level,
            notes=review.notes,
            review_duration_seconds=review.review_duration_seconds
        )
        db.add(db_review)
        db.commit()
        db.refresh(db_review)
        return db_review
    
    def update_review(self, db: Session, review_id: UUID, review_update: ReviewUpdate) -> Optional[Review]:
        """Update existing review"""
        db_review = db.query(Review).filter(Review.id == review_id).first()
        if not db_review:
            return None
        
        update_data = review_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_review, field, value)
        
        db.commit()
        db.refresh(db_review)
        return db_review
    
    def delete_review(self, db: Session, review_id: UUID) -> bool:
        """Delete review"""
        db_review = db.query(Review).filter(Review.id == review_id).first()
        if not db_review:
            return False
        
        db.delete(db_review)
        db.commit()
        return True
    
    def assign_review(self, db: Session, detection_id: UUID, reviewer_id: UUID) -> Optional[Review]:
        """Assign a detection for review"""
        # Check if review already exists for this detection
        existing_review = db.query(Review).filter(Review.detection_id == detection_id).first()
        if existing_review:
            return existing_review
        
        # Create new review assignment
        review_create = ReviewCreate(detection_id=detection_id)
        return self.create_review(db, review_create, reviewer_id)
    
    def get_reviewer_workload(self, db: Session, reviewer_id: UUID) -> Dict[str, int]:
        """Get current workload for a reviewer"""
        pending = (
            db.query(func.count(Review.id))
            .filter(
                Review.reviewer_id == reviewer_id,
                Review.review_status == ReviewStatus.PENDING
            )
            .scalar() or 0
        )
        
        completed_today = (
            db.query(func.count(Review.id))
            .filter(
                Review.reviewer_id == reviewer_id,
                Review.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.REJECTED]),
                func.date(Review.reviewed_at) == func.date(func.now())
            )
            .scalar() or 0
        )
        
        return {
            "pending": pending,
            "completed_today": completed_today
        }
    
    def get_review_stats(self, db: Session, days: int = 7) -> Dict[str, Any]:
        """Get review statistics for the specified period"""
        start_date = datetime.now() - timedelta(days=days)
        
        # Overall stats
        total_pending = (
            db.query(func.count(Review.id))
            .filter(Review.review_status == ReviewStatus.PENDING)
            .scalar() or 0
        )
        
        total_approved = (
            db.query(func.count(Review.id))
            .filter(
                Review.review_status == ReviewStatus.APPROVED,
                Review.reviewed_at >= start_date
            )
            .scalar() or 0
        )
        
        total_rejected = (
            db.query(func.count(Review.id))
            .filter(
                Review.review_status == ReviewStatus.REJECTED,
                Review.reviewed_at >= start_date
            )
            .scalar() or 0
        )
        
        # Average review time
        avg_review_time = (
            db.query(func.avg(Review.review_duration_seconds))
            .filter(
                Review.review_status.in_([ReviewStatus.APPROVED, ReviewStatus.REJECTED]),
                Review.reviewed_at >= start_date
            )
            .scalar()
        )
        
        # Reviewer stats
        reviewer_stats = (
            db.query(
                User.username,
                Review.review_status,
                func.count(Review.id).label('count')
            )
            .join(Review, User.id == Review.reviewer_id)
            .filter(Review.reviewed_at >= start_date)
            .group_by(User.username, Review.review_status)
            .all()
        )
        
        # Process reviewer stats into dictionary
        reviewer_dict = {}
        for username, status, count in reviewer_stats:
            if username not in reviewer_dict:
                reviewer_dict[username] = {}
            reviewer_dict[username][status] = count
        
        return {
            "total_pending": total_pending,
            "total_approved": total_approved,
            "total_rejected": total_rejected,
            "avg_review_time": avg_review_time,
            "reviewer_stats": reviewer_dict
        }


class DetectionCRUD:
    def get_detection(self, db: Session, detection_id: UUID) -> Optional[Detection]:
        """Get detection by ID"""
        return db.query(Detection).filter(Detection.id == detection_id).first()
    
    def get_detections_for_review(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 20,
        is_anomaly: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        unreviewed_only: bool = False
    ) -> Tuple[List[Detection], int]:
        """Get detections that need review"""
        query = db.query(Detection).options(
            joinedload(Detection.image),
            joinedload(Detection.reviews)
        )
        
        # Apply filters
        if is_anomaly is not None:
            query = query.filter(Detection.is_anomaly == is_anomaly)
        
        if min_confidence is not None:
            query = query.filter(Detection.confidence_score >= min_confidence)
        
        if unreviewed_only:
            # Only show detections without reviews
            query = query.outerjoin(Review).filter(Review.id.is_(None))
        
        # Order by confidence score (lowest first for anomalies, highest first for normal)
        query = query.order_by(Detection.confidence_score)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        detections = query.offset(skip).limit(limit).all()
        
        return detections, total


# Global CRUD instances
review_crud = ReviewCRUD()
detection_crud = DetectionCRUD()