import asyncio
import logging
import signal
import sys
import time
from threading import Thread
from pathlib import Path
import torch

from app.config import settings
from app.database import init_db
from app.image_processor import ImageProcessor
from app.queue_consumer import RabbitMQConsumer, MessagePublisher
from app.metrics import MLMetrics, get_metrics
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


class MLWorkerService:
    """Main ML Worker service class"""
    
    def __init__(self):
        self.image_processor = None
        self.consumer = None
        self.publisher = None
        self.metrics = MLMetrics()
        self.running = False
        self.health_status = False
        
    async def initialize(self):
        """Initialize all components"""
        try:
            logger.info("Initializing ML Worker Service")
            
            # Initialize database
            init_db()
            logger.info("Database initialized")
            
            # Check GPU availability
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"GPU available: {gpu_name} (count: {gpu_count})")
            else:
                logger.warning("No GPU available, using CPU")
            
            # Initialize image processor
            self.image_processor = ImageProcessor()
            await self.image_processor.initialize()
            logger.info("Image processor initialized")
            
            # Initialize message publisher
            self.publisher = MessagePublisher()
            self.publisher.connect()
            logger.info("Message publisher initialized")
            
            # Initialize consumer with message handler
            self.consumer = RabbitMQConsumer(self._handle_message)
            self.consumer.connect()
            logger.info("Message consumer initialized")
            
            # Update metrics
            self.metrics.update_model_status(self.image_processor.model_loaded)
            self.metrics.update_system_health(True)
            
            self.health_status = True
            logger.info("ML Worker Service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize ML Worker Service", error=str(e))
            self.health_status = False
            raise
    
    async def _handle_message(self, message_data: dict) -> dict:
        """Handle incoming processing message"""
        message_id = message_data.get('message_id', 'unknown')
        
        try:
            logger.info("Processing message", message_id=message_id)
            
            # Record queue message
            self.metrics.record_queue_message('received')
            
            # Process the image
            result = await self.image_processor.process_image(message_data)
            
            # Send notification if anomaly detected
            if result.get('success') and result.get('is_anomaly'):
                await self._send_anomaly_notification(result)
            
            # Record success
            self.metrics.record_queue_message('success')
            self.metrics.record_image_processed('success')
            
            return result
            
        except Exception as e:
            logger.error("Message processing failed", message_id=message_id, error=str(e))
            
            # Record error
            self.metrics.record_error(type(e).__name__)
            self.metrics.record_queue_message('error')
            
            raise
    
    async def _send_anomaly_notification(self, result: dict):
        """Send notification for detected anomaly"""
        try:
            notification_data = {
                'type': 'anomaly_detected',
                'image_id': result['image_id'],
                'detection_id': result['detection_id'],
                'confidence': result['confidence'],
                'timestamp': time.time()
            }
            
            self.publisher.publish_notification('anomaly_detected', notification_data)
            logger.info("Anomaly notification sent", **notification_data)
            
        except Exception as e:
            logger.error("Failed to send anomaly notification", error=str(e))
    
    def start_consumer(self):
        """Start the message consumer in a separate thread"""
        def consumer_thread():
            try:
                logger.info("Starting message consumer")
                self.consumer.start_consuming()
            except Exception as e:
                logger.error("Consumer error", error=str(e))
                self.health_status = False
        
        thread = Thread(target=consumer_thread, daemon=True)
        thread.start()
        return thread
    
    def start_metrics_server(self):
        """Start metrics server"""
        def metrics_server():
            from wsgiref.simple_server import make_server
            from app.metrics import create_metrics_app
            
            try:
                app = create_metrics_app()
                server = make_server('0.0.0.0', settings.metrics_port, app)
                logger.info(f"Metrics server started on port {settings.metrics_port}")
                server.serve_forever()
            except Exception as e:
                logger.error("Metrics server error", error=str(e))
        
        if settings.metrics_enabled:
            thread = Thread(target=metrics_server, daemon=True)
            thread.start()
            return thread
        
        return None
    
    async def start_health_monitor(self):
        """Start health monitoring loop"""
        while self.running:
            try:
                # Update GPU metrics if available
                if torch.cuda.is_available():
                    allocated = torch.cuda.memory_allocated(0)
                    reserved = torch.cuda.memory_reserved(0)
                    total_memory = torch.cuda.get_device_properties(0).total_memory
                    free = total_memory - allocated
                    
                    self.metrics.update_gpu_metrics(allocated, free)
                
                # Update processing thread count
                import threading
                active_threads = threading.active_count()
                self.metrics.update_active_threads(active_threads)
                
                # Check processor health
                processor_health = await self.image_processor.health_check()
                if processor_health.get('status') != 'healthy':
                    self.health_status = False
                    logger.warning("Image processor unhealthy", **processor_health)
                
                # Check consumer health
                consumer_health = self.consumer.health_check()
                if consumer_health.get('status') != 'healthy':
                    self.health_status = False
                    logger.warning("Consumer unhealthy", **consumer_health)
                
                # Update system health
                self.metrics.update_system_health(self.health_status)
                
            except Exception as e:
                logger.error("Health monitor error", error=str(e))
                self.health_status = False
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def run(self):
        """Main service loop"""
        try:
            await self.initialize()
            
            self.running = True
            
            # Start consumer thread
            consumer_thread = self.start_consumer()
            
            # Start metrics server
            metrics_thread = self.start_metrics_server()
            
            # Start health monitor
            health_task = asyncio.create_task(self.start_health_monitor())
            
            logger.info("ML Worker Service is running")
            
            # Keep main thread alive
            while self.running:
                await asyncio.sleep(1)
                
                # Check if consumer thread died
                if not consumer_thread.is_alive():
                    logger.error("Consumer thread died, restarting...")
                    consumer_thread = self.start_consumer()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error("Service error", error=str(e))
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Cleanup and shutdown"""
        logger.info("Shutting down ML Worker Service")
        
        self.running = False
        self.metrics.update_system_health(False)
        
        # Close consumer
        if self.consumer:
            self.consumer.disconnect()
        
        # Close publisher
        if self.publisher:
            self.publisher.close()
        
        logger.info("ML Worker Service shutdown complete")
    
    def get_service_info(self):
        """Get service information"""
        return {
            "service": "ml-worker",
            "version": settings.model_version,
            "status": "running" if self.running else "stopped",
            "health": "healthy" if self.health_status else "unhealthy",
            "gpu_available": torch.cuda.is_available(),
            "model_loaded": self.image_processor.model_loaded if self.image_processor else False,
            "processing_stats": self.image_processor.get_stats() if self.image_processor else {},
            "metrics": self.metrics.get_metrics_summary()
        }


# Global service instance
service = None


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if service:
        asyncio.create_task(service.shutdown())
    sys.exit(0)


async def main():
    """Main entry point"""
    global service
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run service
    service = MLWorkerService()
    
    try:
        await service.run()
    except Exception as e:
        logger.error("Service failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    # Set log level
    logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
    
    # Create model directory if it doesn't exist
    Path(settings.model_path).mkdir(parents=True, exist_ok=True)
    
    # Run service
    asyncio.run(main())