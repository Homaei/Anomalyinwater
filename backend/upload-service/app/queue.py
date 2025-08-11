import pika
import json
import structlog
from app.config import settings
from typing import Dict, Any

logger = structlog.get_logger()

class RabbitMQConnection:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.connect()
    
    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            parameters = pika.URLParameters(settings.rabbitmq_url)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare queues
            self.channel.queue_declare(queue='ml_processing', durable=True)
            self.channel.queue_declare(queue='notifications', durable=True)
            
            logger.info("Connected to RabbitMQ")
            
        except Exception as e:
            logger.error("Failed to connect to RabbitMQ", error=str(e))
            raise
    
    def close(self):
        """Close RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
    
    def send_message(self, queue_name: str, message: Dict[Any, Any]):
        """Send message to queue"""
        try:
            if not self.connection or self.connection.is_closed:
                self.connect()
            
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )
            logger.info("Message sent to queue", queue=queue_name, message_id=message.get('image_id'))
            
        except Exception as e:
            logger.error("Failed to send message", queue=queue_name, error=str(e))
            raise

# Global connection instance
rabbitmq_connection = RabbitMQConnection()

def check_connection():
    """Check RabbitMQ connection"""
    try:
        if not rabbitmq_connection.connection or rabbitmq_connection.connection.is_closed:
            rabbitmq_connection.connect()
        return True
    except Exception as e:
        logger.error("RabbitMQ connection check failed", error=str(e))
        raise

async def send_to_ml_queue(message: Dict[Any, Any]):
    """Send message to ML processing queue"""
    try:
        rabbitmq_connection.send_message('ml_processing', message)
    except Exception as e:
        logger.error("Failed to send to ML queue", error=str(e))
        raise

async def send_notification(message: Dict[Any, Any]):
    """Send notification message"""
    try:
        rabbitmq_connection.send_message('notifications', message)
    except Exception as e:
        logger.error("Failed to send notification", error=str(e))
        raise