from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry
from prometheus_client.exposition import make_wsgi_app
import time
import logging
from typing import Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

# Create custom registry for ML Worker metrics
registry = CollectorRegistry()

# Processing metrics
images_processed_total = Counter(
    'ml_images_processed_total',
    'Total number of images processed',
    ['status'],
    registry=registry
)

processing_duration_seconds = Histogram(
    'ml_processing_duration_seconds',
    'Image processing duration in seconds',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    registry=registry
)

anomalies_detected_total = Counter(
    'ml_anomalies_detected_total',
    'Total number of anomalies detected',
    registry=registry
)

confidence_score_histogram = Histogram(
    'ml_confidence_score',
    'Distribution of confidence scores',
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=registry
)

model_inference_duration_seconds = Histogram(
    'ml_model_inference_duration_seconds',
    'Model inference duration in seconds',
    registry=registry
)

# Queue metrics
queue_messages_processed_total = Counter(
    'ml_queue_messages_processed_total',
    'Total queue messages processed',
    ['status'],
    registry=registry
)

queue_processing_errors_total = Counter(
    'ml_queue_processing_errors_total',
    'Total queue processing errors',
    ['error_type'],
    registry=registry
)

# Model metrics
model_status = Gauge(
    'ml_model_status',
    'Model status (1=loaded, 0=not loaded)',
    registry=registry
)

model_memory_usage_bytes = Gauge(
    'ml_model_memory_usage_bytes',
    'Model memory usage in bytes',
    registry=registry
)

gpu_memory_allocated_bytes = Gauge(
    'ml_gpu_memory_allocated_bytes',
    'GPU memory allocated in bytes',
    registry=registry
)

gpu_memory_free_bytes = Gauge(
    'ml_gpu_memory_free_bytes',
    'GPU memory free in bytes',
    registry=registry
)

gpu_utilization_percent = Gauge(
    'ml_gpu_utilization_percent',
    'GPU utilization percentage',
    registry=registry
)

# Business metrics
anomaly_detection_accuracy = Gauge(
    'ml_anomaly_detection_accuracy',
    'Anomaly detection accuracy',
    registry=registry
)

false_positive_rate = Gauge(
    'ml_false_positive_rate',
    'False positive rate',
    registry=registry
)

false_negative_rate = Gauge(
    'ml_false_negative_rate',
    'False negative rate',
    registry=registry
)

# System metrics
system_health_status = Gauge(
    'ml_system_health_status',
    'System health status (1=healthy, 0=unhealthy)',
    registry=registry
)

active_processing_threads = Gauge(
    'ml_active_processing_threads',
    'Number of active processing threads',
    registry=registry
)


class MLMetrics:
    """ML Worker metrics collector"""
    
    def __init__(self):
        self.enabled = settings.metrics_enabled
        self.start_time = time.time()
    
    def record_image_processed(self, status: str = 'success'):
        """Record image processing completion"""
        if not self.enabled:
            return
        
        images_processed_total.labels(status=status).inc()
    
    def record_processing_time(self, duration: float):
        """Record processing time in seconds"""
        if not self.enabled:
            return
        
        processing_duration_seconds.observe(duration)
    
    def record_detection(self, is_anomaly: bool, confidence: float):
        """Record detection result"""
        if not self.enabled:
            return
        
        if is_anomaly:
            anomalies_detected_total.inc()
        
        confidence_score_histogram.observe(confidence)
    
    def record_model_inference_time(self, duration: float):
        """Record model inference time"""
        if not self.enabled:
            return
        
        model_inference_duration_seconds.observe(duration)
    
    def record_queue_message(self, status: str = 'success'):
        """Record queue message processing"""
        if not self.enabled:
            return
        
        queue_messages_processed_total.labels(status=status).inc()
    
    def record_error(self, error_type: str):
        """Record processing error"""
        if not self.enabled:
            return
        
        queue_processing_errors_total.labels(error_type=error_type).inc()
        images_processed_total.labels(status='error').inc()
    
    def update_model_status(self, is_loaded: bool):
        """Update model status"""
        if not self.enabled:
            return
        
        model_status.set(1 if is_loaded else 0)
    
    def update_memory_usage(self, memory_bytes: float):
        """Update model memory usage"""
        if not self.enabled:
            return
        
        model_memory_usage_bytes.set(memory_bytes)
    
    def update_gpu_metrics(self, allocated: float, free: float, utilization: float = None):
        """Update GPU metrics"""
        if not self.enabled:
            return
        
        gpu_memory_allocated_bytes.set(allocated)
        gpu_memory_free_bytes.set(free)
        
        if utilization is not None:
            gpu_utilization_percent.set(utilization)
    
    def update_business_metrics(
        self,
        accuracy: float = None,
        false_positive_rate_val: float = None,
        false_negative_rate_val: float = None
    ):
        """Update business metrics"""
        if not self.enabled:
            return
        
        if accuracy is not None:
            anomaly_detection_accuracy.set(accuracy)
        
        if false_positive_rate_val is not None:
            false_positive_rate.set(false_positive_rate_val)
        
        if false_negative_rate_val is not None:
            false_negative_rate.set(false_negative_rate_val)
    
    def update_system_health(self, is_healthy: bool):
        """Update system health status"""
        if not self.enabled:
            return
        
        system_health_status.set(1 if is_healthy else 0)
    
    def update_active_threads(self, count: int):
        """Update active processing thread count"""
        if not self.enabled:
            return
        
        active_processing_threads.set(count)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        if not self.enabled:
            return {"status": "disabled"}
        
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": uptime,
            "images_processed": images_processed_total._value.sum(),
            "anomalies_detected": anomalies_detected_total._value.sum(),
            "processing_errors": sum(
                counter._value.sum() 
                for counter in queue_processing_errors_total._metrics.values()
            ),
            "model_loaded": bool(model_status._value.get()),
            "gpu_memory_allocated_gb": gpu_memory_allocated_bytes._value.get() / 1e9,
            "gpu_memory_free_gb": gpu_memory_free_bytes._value.get() / 1e9,
        }


def get_metrics():
    """Get metrics in Prometheus format"""
    return generate_latest(registry)


def create_metrics_app():
    """Create WSGI app for metrics endpoint"""
    return make_wsgi_app(registry)