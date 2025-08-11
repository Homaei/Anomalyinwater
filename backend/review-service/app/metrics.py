from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry
from prometheus_client.exposition import make_wsgi_app
from functools import wraps
import time
import logging
from typing import Callable
from app.config import settings

logger = logging.getLogger(__name__)

# Create custom registry
registry = CollectorRegistry()

# Define metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

websocket_connections_total = Gauge(
    'websocket_connections_total',
    'Total WebSocket connections',
    registry=registry
)

reviews_processed_total = Counter(
    'reviews_processed_total',
    'Total reviews processed',
    ['status', 'verdict'],
    registry=registry
)

review_processing_duration_seconds = Histogram(
    'review_processing_duration_seconds',
    'Review processing duration in seconds',
    registry=registry
)

detections_processed_total = Counter(
    'detections_processed_total',
    'Total detections processed',
    ['is_anomaly'],
    registry=registry
)

database_operations_total = Counter(
    'database_operations_total',
    'Total database operations',
    ['operation', 'table'],
    registry=registry
)

database_operation_duration_seconds = Histogram(
    'database_operation_duration_seconds',
    'Database operation duration in seconds',
    ['operation', 'table'],
    registry=registry
)

auth_requests_total = Counter(
    'auth_requests_total',
    'Total authentication requests',
    ['status'],
    registry=registry
)

system_health_status = Gauge(
    'system_health_status',
    'System health status (1=healthy, 0=unhealthy)',
    registry=registry
)

# Business metrics
pending_reviews_total = Gauge(
    'pending_reviews_total',
    'Total pending reviews',
    registry=registry
)

avg_review_time_seconds = Gauge(
    'avg_review_time_seconds',
    'Average review time in seconds',
    registry=registry
)

anomaly_detection_accuracy = Gauge(
    'anomaly_detection_accuracy',
    'Anomaly detection accuracy rate',
    registry=registry
)


class MetricsCollector:
    def __init__(self):
        self.enabled = settings.metrics_enabled
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics"""
        if not self.enabled:
            return
        
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_websocket_connection(self, count: int):
        """Record WebSocket connection count"""
        if not self.enabled:
            return
        
        websocket_connections_total.set(count)
    
    def record_review_processed(self, status: str, verdict: str = None, duration: float = None):
        """Record review processing metrics"""
        if not self.enabled:
            return
        
        reviews_processed_total.labels(
            status=status,
            verdict=verdict or "unknown"
        ).inc()
        
        if duration is not None:
            review_processing_duration_seconds.observe(duration)
    
    def record_detection_processed(self, is_anomaly: bool):
        """Record detection processing metrics"""
        if not self.enabled:
            return
        
        detections_processed_total.labels(
            is_anomaly=str(is_anomaly).lower()
        ).inc()
    
    def record_database_operation(self, operation: str, table: str, duration: float):
        """Record database operation metrics"""
        if not self.enabled:
            return
        
        database_operations_total.labels(
            operation=operation,
            table=table
        ).inc()
        
        database_operation_duration_seconds.labels(
            operation=operation,
            table=table
        ).observe(duration)
    
    def record_auth_request(self, status: str):
        """Record authentication request metrics"""
        if not self.enabled:
            return
        
        auth_requests_total.labels(status=status).inc()
    
    def update_system_health(self, is_healthy: bool):
        """Update system health status"""
        if not self.enabled:
            return
        
        system_health_status.set(1 if is_healthy else 0)
    
    def update_business_metrics(
        self,
        pending_reviews: int = None,
        avg_review_time: float = None,
        detection_accuracy: float = None
    ):
        """Update business metrics"""
        if not self.enabled:
            return
        
        if pending_reviews is not None:
            pending_reviews_total.set(pending_reviews)
        
        if avg_review_time is not None:
            avg_review_time_seconds.set(avg_review_time)
        
        if detection_accuracy is not None:
            anomaly_detection_accuracy.set(detection_accuracy)


# Global metrics collector
metrics = MetricsCollector()


def track_time(operation: str, table: str = None):
    """Decorator to track operation timing"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                if table:
                    metrics.record_database_operation(operation, table, duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                if table:
                    metrics.record_database_operation(f"{operation}_error", table, duration)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                if table:
                    metrics.record_database_operation(operation, table, duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                if table:
                    metrics.record_database_operation(f"{operation}_error", table, duration)
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def get_metrics():
    """Get metrics in Prometheus format"""
    return generate_latest(registry)


def create_metrics_app():
    """Create WSGI app for metrics endpoint"""
    return make_wsgi_app(registry)