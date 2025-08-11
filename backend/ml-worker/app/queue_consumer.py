import pika
import json
import asyncio
import logging
import time
from typing import Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)


class RabbitMQConsumer:
    """RabbitMQ consumer for processing image analysis messages"""
    
    def __init__(self, message_handler: Callable):
        self.connection = None
        self.channel = None
        self.message_handler = message_handler
        self.executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_processing)
        self.is_connected = False
        
    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            # Parse connection URL
            connection_params = pika.URLParameters(settings.rabbitmq_url)
            
            # Create connection with heartbeat
            self.connection = pika.BlockingConnection(connection_params)
            self.channel = self.connection.channel()
            
            # Declare exchange
            self.channel.exchange_declare(
                exchange=settings.rabbitmq_exchange,
                exchange_type='direct',
                durable=True
            )
            
            # Declare queue
            self.channel.queue_declare(
                queue=settings.rabbitmq_queue,
                durable=True,
                arguments={
                    'x-max-priority': 10,  # Enable priority queue
                    'x-message-ttl': 3600000,  # 1 hour TTL
                }
            )
            
            # Bind queue to exchange
            self.channel.queue_bind(
                exchange=settings.rabbitmq_exchange,
                queue=settings.rabbitmq_queue,
                routing_key='image.analyze'
            )
            
            # Set QoS to process one message at a time per worker
            self.channel.basic_qos(prefetch_count=1)
            
            self.is_connected = True
            logger.info("Connected to RabbitMQ successfully")
            
        except Exception as e:
            logger.error("Failed to connect to RabbitMQ", error=str(e))
            self.is_connected = False
            raise
    
    def disconnect(self):
        """Close RabbitMQ connection"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            
            self.is_connected = False
            logger.info("Disconnected from RabbitMQ")
            
        except Exception as e:
            logger.error("Error disconnecting from RabbitMQ", error=str(e))
    
    def process_message(self, channel, method, properties, body):
        """Process incoming message"""
        delivery_tag = method.delivery_tag
        
        try:
            # Decode message
            message_data = json.loads(body.decode('utf-8'))
            
            logger.info(
                "Processing message",
                message_id=message_data.get('message_id'),
                image_id=message_data.get('image_id'),
                priority=properties.priority
            )
            
            # Submit to thread pool for processing
            future = self.executor.submit(self._handle_message_sync, message_data, delivery_tag)
            
            # Process in background - acknowledgment handled in _handle_message_sync
            
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in message", error=str(e))
            channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error("Error processing message", error=str(e))
            channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
    
    def _handle_message_sync(self, message_data: Dict[str, Any], delivery_tag: int):
        """Handle message in thread pool (sync version)"""
        start_time = time.time()
        success = False
        
        try:
            # Run the async message handler in the thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    self.message_handler(message_data)
                )
                success = True
                
                # Acknowledge message
                self.channel.basic_ack(delivery_tag=delivery_tag)
                
                processing_time = (time.time() - start_time) * 1000
                logger.info(
                    "Message processed successfully",
                    message_id=message_data.get('message_id'),
                    processing_time_ms=processing_time,
                    result=result
                )
                
            except Exception as e:
                logger.error(
                    "Message handler failed",
                    message_id=message_data.get('message_id'),
                    error=str(e)
                )
                
                # Determine if message should be requeued
                requeue = self._should_requeue(message_data, e)
                self.channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error("Critical error in message handling", error=str(e))
            try:
                self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
            except:
                pass  # Connection might be lost
    
    def _should_requeue(self, message_data: Dict[str, Any], error: Exception) -> bool:
        """Determine if message should be requeued based on error type"""
        # Get retry count
        retry_count = message_data.get('retry_count', 0)
        
        # Don't requeue if max retries reached
        if retry_count >= settings.retry_attempts:
            logger.warning(
                "Max retries reached, discarding message",
                message_id=message_data.get('message_id'),
                retry_count=retry_count
            )
            return False
        
        # Don't requeue for certain error types
        non_retryable_errors = [
            FileNotFoundError,  # Image file not found
            ValueError,  # Invalid image format
            json.JSONDecodeError,  # Invalid message format
        ]
        
        if any(isinstance(error, err_type) for err_type in non_retryable_errors):
            logger.warning(
                "Non-retryable error, discarding message",
                message_id=message_data.get('message_id'),
                error_type=type(error).__name__
            )
            return False
        
        return True
    
    def start_consuming(self):
        """Start consuming messages"""
        if not self.is_connected:
            self.connect()
        
        logger.info(f"Starting to consume messages from queue: {settings.rabbitmq_queue}")
        
        # Set up consumer
        self.channel.basic_consume(
            queue=settings.rabbitmq_queue,
            on_message_callback=self.process_message,
            auto_ack=False  # Manual acknowledgment
        )
        
        try:
            # Start consuming
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            logger.info("Stopping consumer...")
            self.channel.stop_consuming()
            
        except Exception as e:
            logger.error("Consumer error", error=str(e))
            raise
        
        finally:
            self.disconnect()
    
    def publish_result(self, routing_key: str, message: Dict[str, Any], priority: int = 0):
        """Publish processing result"""
        try:
            if not self.is_connected:
                self.connect()
            
            self.channel.basic_publish(
                exchange=settings.rabbitmq_exchange,
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    priority=priority,
                    content_type='application/json',
                    timestamp=int(time.time())
                )
            )
            
            logger.info(
                "Result published",
                routing_key=routing_key,
                message_id=message.get('message_id')
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish result",
                error=str(e),
                routing_key=routing_key
            )
            raise
    
    def health_check(self) -> Dict[str, Any]:
        """Check consumer health"""
        try:
            if not self.is_connected or self.connection.is_closed:
                return {
                    "status": "unhealthy",
                    "connected": False,
                    "error": "Not connected to RabbitMQ"
                }
            
            # Check queue status
            method = self.channel.queue_declare(
                queue=settings.rabbitmq_queue,
                passive=True  # Don't create, just check
            )
            
            return {
                "status": "healthy",
                "connected": True,
                "queue": settings.rabbitmq_queue,
                "message_count": method.method.message_count,
                "consumer_count": method.method.consumer_count
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


class MessagePublisher:
    """Utility class for publishing messages to RabbitMQ"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Connect to RabbitMQ"""
        connection_params = pika.URLParameters(settings.rabbitmq_url)
        self.connection = pika.BlockingConnection(connection_params)
        self.channel = self.connection.channel()
        
        # Declare exchange
        self.channel.exchange_declare(
            exchange=settings.rabbitmq_exchange,
            exchange_type='direct',
            durable=True
        )
    
    def publish_notification(self, notification_type: str, data: Dict[str, Any]):
        """Publish notification message"""
        if not self.connection or self.connection.is_closed:
            self.connect()
        
        message = {
            'type': notification_type,
            'data': data,
            'timestamp': time.time(),
            'source': 'ml-worker'
        }
        
        self.channel.basic_publish(
            exchange=settings.rabbitmq_exchange,
            routing_key=f'notification.{notification_type}',
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type='application/json'
            )
        )
    
    def close(self):
        """Close connection"""
        if self.channel and not self.channel.is_closed:
            self.channel.close()
        if self.connection and not self.connection.is_closed:
            self.connection.close()