from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    
    # RabbitMQ
    rabbitmq_url: str = Field(..., env="RABBITMQ_URL")
    rabbitmq_queue: str = Field("image_processing", env="RABBITMQ_QUEUE")
    rabbitmq_exchange: str = Field("wwtp_exchange", env="RABBITMQ_EXCHANGE")
    
    # Redis for caching
    redis_url: str = Field("redis://redis:6379", env="REDIS_URL")
    
    # ML Model Configuration
    model_path: str = Field("/app/models", env="MODEL_PATH")
    model_name: str = Field("resnet_anomaly_detector.pth", env="MODEL_NAME")
    model_version: str = Field("1.0.0", env="MODEL_VERSION")
    
    # Image Processing
    image_size: int = Field(224, env="IMAGE_SIZE")
    batch_size: int = Field(16, env="BATCH_SIZE")
    max_image_size: int = Field(10 * 1024 * 1024, env="MAX_IMAGE_SIZE")  # 10MB
    
    # Detection Thresholds
    anomaly_threshold: float = Field(0.7, env="ANOMALY_THRESHOLD")
    confidence_threshold: float = Field(0.5, env="CONFIDENCE_THRESHOLD")
    
    # GPU Configuration
    use_gpu: bool = Field(True, env="USE_GPU")
    gpu_device: int = Field(0, env="GPU_DEVICE")
    
    # Processing Configuration
    max_concurrent_processing: int = Field(4, env="MAX_CONCURRENT_PROCESSING")
    processing_timeout: int = Field(300, env="PROCESSING_TIMEOUT")  # 5 minutes
    retry_attempts: int = Field(3, env="RETRY_ATTEMPTS")
    retry_delay: int = Field(5, env="RETRY_DELAY")  # seconds
    
    # Data Augmentation
    use_augmentation: bool = Field(False, env="USE_AUGMENTATION")  # Disabled for inference
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    # Metrics
    metrics_enabled: bool = Field(True, env="METRICS_ENABLED")
    metrics_port: int = Field(8080, env="METRICS_PORT")
    
    # Model Training (if enabled)
    enable_training: bool = Field(False, env="ENABLE_TRAINING")
    training_data_path: str = Field("/app/training_data", env="TRAINING_DATA_PATH")
    validation_split: float = Field(0.2, env="VALIDATION_SPLIT")
    learning_rate: float = Field(0.001, env="LEARNING_RATE")
    epochs: int = Field(50, env="EPOCHS")
    early_stopping_patience: int = Field(10, env="EARLY_STOPPING_PATIENCE")
    
    # Model Performance
    min_model_accuracy: float = Field(0.85, env="MIN_MODEL_ACCURACY")
    max_inference_time_ms: int = Field(1000, env="MAX_INFERENCE_TIME_MS")
    
    class Config:
        env_file = ".env"


settings = Settings()