import cv2
import numpy as np
from PIL import Image
import torch
import asyncio
import aiofiles
from pathlib import Path
import logging
import time
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session

from app.database import get_db, Image as ImageModel, Detection as DetectionModel
from app.models import ModelManager
from app.config import settings
from app.metrics import MLMetrics
import structlog

logger = structlog.get_logger(__name__)


class ImageProcessor:
    """Main image processing class for anomaly detection"""
    
    def __init__(self):
        # Setup device
        self.device = self._setup_device()
        
        # Initialize model manager
        self.model_manager = ModelManager(settings.model_path, self.device)
        self.model_loaded = False
        
        # Metrics
        self.metrics = MLMetrics()
        
        # Processing stats
        self.stats = {
            'processed_images': 0,
            'anomalies_detected': 0,
            'processing_errors': 0,
            'total_processing_time': 0.0
        }
    
    def _setup_device(self) -> torch.device:
        """Setup PyTorch device (GPU/CPU)"""
        if settings.use_gpu and torch.cuda.is_available():
            device = torch.device(f'cuda:{settings.gpu_device}')
            logger.info(f"Using GPU: {torch.cuda.get_device_name(device)}")
            
            # Log GPU memory info
            total_memory = torch.cuda.get_device_properties(device).total_memory / 1e9
            logger.info(f"GPU memory: {total_memory:.1f} GB")
            
        else:
            device = torch.device('cpu')
            logger.info("Using CPU for inference")
            
        return device
    
    async def initialize(self):
        """Initialize the processor"""
        try:
            # Load model
            self.model_loaded = self.model_manager.load_model(settings.model_name)
            
            if not self.model_loaded:
                logger.warning("Model not loaded, predictions will use dummy results")
            else:
                logger.info("Image processor initialized successfully")
                
                # Log model info
                model_info = self.model_manager.get_model_info()
                logger.info("Model information", **model_info)
            
        except Exception as e:
            logger.error("Failed to initialize image processor", error=str(e))
            raise
    
    async def process_image(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process image for anomaly detection
        
        Args:
            message_data: Message containing image information
            
        Returns:
            Processing result
        """
        start_time = time.time()
        image_id = message_data.get('image_id')
        
        try:
            logger.info("Starting image processing", image_id=image_id)
            
            # Get image information from database
            db_session = next(get_db())
            try:
                image_record = db_session.query(ImageModel).filter(
                    ImageModel.id == image_id
                ).first()
                
                if not image_record:
                    raise FileNotFoundError(f"Image record {image_id} not found in database")
                
                # Update processing status
                image_record.processing_status = 'processing'
                db_session.commit()
                
                # Load and validate image
                image_path = Path(image_record.file_path)
                if not image_path.exists():
                    raise FileNotFoundError(f"Image file not found: {image_path}")
                
                # Load image
                image = await self._load_image(image_path)
                
                # Validate image
                self._validate_image(image, image_record)
                
                # Run anomaly detection
                detection_result = await self._detect_anomaly(image, image_record)
                
                # Save detection to database
                detection_record = await self._save_detection(
                    db_session, image_record, detection_result
                )
                
                # Update image processing status
                image_record.processing_status = 'completed'
                db_session.commit()
                
                # Update metrics
                processing_time = time.time() - start_time
                self.metrics.record_processing_time(processing_time)
                self.metrics.record_detection(
                    detection_result['is_anomaly'],
                    detection_result['confidence']
                )
                
                # Update internal stats
                self.stats['processed_images'] += 1
                self.stats['total_processing_time'] += processing_time
                if detection_result['is_anomaly']:
                    self.stats['anomalies_detected'] += 1
                
                logger.info(
                    "Image processing completed",
                    image_id=image_id,
                    processing_time_ms=processing_time * 1000,
                    is_anomaly=detection_result['is_anomaly'],
                    confidence=detection_result['confidence']
                )
                
                return {
                    'success': True,
                    'image_id': str(image_id),
                    'detection_id': str(detection_record.id),
                    'is_anomaly': detection_result['is_anomaly'],
                    'confidence': detection_result['confidence'],
                    'processing_time_ms': processing_time * 1000
                }
                
            finally:
                db_session.close()
                
        except Exception as e:
            # Update error stats
            self.stats['processing_errors'] += 1
            self.metrics.record_error(type(e).__name__)
            
            # Update database status
            try:
                db_session = next(get_db())
                image_record = db_session.query(ImageModel).filter(
                    ImageModel.id == image_id
                ).first()
                if image_record:
                    image_record.processing_status = 'failed'
                    db_session.commit()
                db_session.close()
            except:
                pass
            
            logger.error(
                "Image processing failed",
                image_id=image_id,
                error=str(e),
                processing_time_ms=(time.time() - start_time) * 1000
            )
            
            return {
                'success': False,
                'image_id': str(image_id),
                'error': str(e),
                'processing_time_ms': (time.time() - start_time) * 1000
            }
    
    async def _load_image(self, image_path: Path) -> np.ndarray:
        """Load image from file"""
        try:
            # Check file size
            file_size = image_path.stat().st_size
            if file_size > settings.max_image_size:
                raise ValueError(f"Image file too large: {file_size} bytes")
            
            # Load image with OpenCV
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError(f"Failed to load image: {image_path}")
            
            # Convert BGR to RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            return image
            
        except Exception as e:
            logger.error(f"Failed to load image {image_path}", error=str(e))
            raise
    
    def _validate_image(self, image: np.ndarray, image_record: ImageModel):
        """Validate loaded image"""
        height, width = image.shape[:2]
        
        # Update image dimensions in database if not set
        if not image_record.width or not image_record.height:
            image_record.width = width
            image_record.height = height
        
        # Validate image properties
        if width < 32 or height < 32:
            raise ValueError(f"Image too small: {width}x{height}")
        
        if width > 4096 or height > 4096:
            logger.warning(f"Large image detected: {width}x{height}")
        
        # Validate image format
        if len(image.shape) != 3 or image.shape[2] != 3:
            raise ValueError(f"Invalid image format: {image.shape}")
    
    async def _detect_anomaly(self, image: np.ndarray, image_record: ImageModel) -> Dict[str, Any]:
        """Run anomaly detection on image"""
        start_time = time.time()
        
        try:
            if not self.model_loaded:
                # Return dummy results if model not loaded
                logger.warning("Model not loaded, returning dummy results")
                return {
                    'is_anomaly': False,
                    'confidence': 0.5,
                    'anomaly_type': None,
                    'bounding_box': None,
                    'features': {'dummy': True},
                    'processing_time_ms': (time.time() - start_time) * 1000
                }
            
            # Preprocess image for model
            processed_image = self._preprocess_image(image)
            
            # Run inference
            is_anomaly, confidence, localization, features = self.model_manager.predict(processed_image)
            
            # Determine anomaly type based on confidence and features
            anomaly_type = self._classify_anomaly_type(confidence, features) if is_anomaly else None
            
            # Apply confidence threshold
            if confidence < settings.confidence_threshold:
                is_anomaly = False
                anomaly_type = None
            
            # Apply anomaly threshold for anomaly classification
            if is_anomaly and confidence < settings.anomaly_threshold:
                is_anomaly = False
                anomaly_type = None
            
            processing_time = (time.time() - start_time) * 1000
            
            return {
                'is_anomaly': is_anomaly,
                'confidence': float(confidence),
                'anomaly_type': anomaly_type,
                'bounding_box': localization,
                'features': features,
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            logger.error("Anomaly detection failed", error=str(e))
            raise
    
    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for anomaly detection"""
        try:
            # Resize if needed (model expects specific size)
            target_size = settings.image_size
            
            height, width = image.shape[:2]
            if height != target_size or width != target_size:
                image = cv2.resize(image, (target_size, target_size), interpolation=cv2.INTER_AREA)
            
            # Normalize to [0, 1]
            image = image.astype(np.float32) / 255.0
            
            return image
            
        except Exception as e:
            logger.error("Image preprocessing failed", error=str(e))
            raise
    
    def _classify_anomaly_type(self, confidence: float, features: Dict) -> str:
        """Classify type of anomaly based on features"""
        # This is a simplified classification - can be enhanced with more sophisticated logic
        
        if confidence > 0.9:
            return "high_confidence_anomaly"
        elif confidence > 0.8:
            return "medium_confidence_anomaly"
        elif confidence > 0.7:
            return "low_confidence_anomaly"
        else:
            return "uncertain_anomaly"
    
    async def _save_detection(self, db_session: Session, image_record: ImageModel, detection_result: Dict) -> DetectionModel:
        """Save detection result to database"""
        try:
            detection = DetectionModel(
                image_id=image_record.id,
                model_version=settings.model_version,
                confidence_score=detection_result['confidence'],
                is_anomaly=detection_result['is_anomaly'],
                anomaly_type=detection_result['anomaly_type'],
                bounding_box=detection_result['bounding_box'],
                features=detection_result['features'],
                processing_time_ms=int(detection_result['processing_time_ms'])
            )
            
            db_session.add(detection)
            db_session.commit()
            db_session.refresh(detection)
            
            return detection
            
        except Exception as e:
            logger.error("Failed to save detection", error=str(e))
            db_session.rollback()
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        avg_processing_time = (
            self.stats['total_processing_time'] / max(self.stats['processed_images'], 1)
        )
        
        return {
            **self.stats,
            'avg_processing_time': avg_processing_time,
            'anomaly_rate': self.stats['anomalies_detected'] / max(self.stats['processed_images'], 1),
            'error_rate': self.stats['processing_errors'] / max(self.stats['processed_images'], 1),
            'model_loaded': self.model_loaded,
            'device': str(self.device),
            'gpu_available': torch.cuda.is_available()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            # Check GPU memory if available
            gpu_info = {}
            if torch.cuda.is_available():
                gpu_info = {
                    'gpu_memory_allocated': torch.cuda.memory_allocated(self.device) / 1e9,
                    'gpu_memory_cached': torch.cuda.memory_reserved(self.device) / 1e9,
                    'gpu_memory_free': (
                        torch.cuda.get_device_properties(self.device).total_memory - 
                        torch.cuda.memory_allocated(self.device)
                    ) / 1e9
                }
            
            return {
                'status': 'healthy',
                'model_loaded': self.model_loaded,
                'device': str(self.device),
                'stats': self.get_stats(),
                **gpu_info
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }