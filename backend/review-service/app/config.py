from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    
    # RabbitMQ
    rabbitmq_url: str = Field(..., env="RABBITMQ_URL")
    
    # Redis
    redis_url: str = Field("redis://redis:6379", env="REDIS_URL")
    
    # JWT
    jwt_secret: str = Field(..., env="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expiration: int = Field(3600, env="JWT_EXPIRATION")  # 1 hour
    
    # Auth Service
    auth_service_url: str = Field("http://auth-service:8000", env="AUTH_SERVICE_URL")
    
    # WebSocket
    websocket_heartbeat_interval: int = Field(30, env="WEBSOCKET_HEARTBEAT_INTERVAL")
    max_websocket_connections: int = Field(100, env="MAX_WEBSOCKET_CONNECTIONS")
    
    # API Configuration
    api_title: str = "WWTP Review Service"
    api_description: str = "Anomaly review and validation service"
    api_version: str = "1.0.0"
    debug: bool = Field(False, env="DEBUG")
    
    # Pagination
    default_page_size: int = Field(20, env="DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(100, env="MAX_PAGE_SIZE")
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    # Metrics
    metrics_enabled: bool = Field(True, env="METRICS_ENABLED")
    
    class Config:
        env_file = ".env"


settings = Settings()