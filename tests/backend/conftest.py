import pytest
import asyncio
from typing import AsyncGenerator, Generator
import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient
import redis
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from testcontainers.rabbitmq import RabbitMqContainer
from PIL import Image
import io

# Test fixtures and utilities


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL test container."""
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis test container."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="session")
def rabbitmq_container():
    """Start a RabbitMQ test container."""
    with RabbitMqContainer("rabbitmq:3.12-management-alpine") as rabbitmq:
        yield rabbitmq


@pytest.fixture(scope="session")
def test_database(postgres_container):
    """Create test database engine and tables."""
    database_url = postgres_container.get_connection_url()
    
    # Import and initialize database
    from backend.auth_service.app.database import Base
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    
    yield database_url
    
    engine.dispose()


@pytest.fixture
def db_session(test_database):
    """Create a database session for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(test_database)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_redis(redis_container):
    """Create a Redis client for testing."""
    redis_client = redis.from_url(redis_container.get_connection_url())
    
    yield redis_client
    
    redis_client.flushall()
    redis_client.close()


@pytest.fixture
def test_user_data():
    """Test user data."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "first_name": "Test",
        "last_name": "User",
        "role": "operator"
    }


@pytest.fixture
def test_admin_user_data():
    """Test admin user data."""
    return {
        "username": "admin",
        "email": "admin@example.com",
        "password": "admin123",
        "first_name": "Admin",
        "last_name": "User",
        "role": "admin"
    }


@pytest.fixture
def test_image_file():
    """Create a test image file."""
    # Create a simple test image
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    
    return {
        'filename': 'test_image.jpg',
        'content': img_bytes.getvalue(),
        'content_type': 'image/jpeg'
    }


@pytest.fixture
def large_test_image_file():
    """Create a larger test image file."""
    img = Image.new('RGB', (1920, 1080), color='blue')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG', quality=90)
    img_bytes.seek(0)
    
    return {
        'filename': 'large_test_image.jpg',
        'content': img_bytes.getvalue(),
        'content_type': 'image/jpeg'
    }


@pytest.fixture
def invalid_image_file():
    """Create an invalid image file."""
    return {
        'filename': 'invalid.txt',
        'content': b'This is not an image',
        'content_type': 'text/plain'
    }


@pytest.fixture
def temp_directory():
    """Create a temporary directory for file operations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_jwt_token():
    """Create a mock JWT token for testing."""
    return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImV4cCI6OTk5OTk5OTk5OX0.mock_token"


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Create authorization headers for testing."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}


@pytest.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    async with AsyncClient() as client:
        yield client


# Test data fixtures
@pytest.fixture
def sample_detection_data():
    """Sample detection data for testing."""
    return {
        "model_version": "1.0.0",
        "confidence_score": 0.85,
        "is_anomaly": True,
        "anomaly_type": "contamination",
        "bounding_box": {
            "x": 100,
            "y": 100,
            "width": 200,
            "height": 150
        },
        "features": {
            "color_variance": 0.7,
            "texture_score": 0.6
        },
        "processing_time_ms": 1500
    }


@pytest.fixture
def sample_review_data():
    """Sample review data for testing."""
    return {
        "review_status": "approved",
        "human_verdict": "true_positive",
        "confidence_level": 4,
        "notes": "Clear contamination visible",
        "review_duration_seconds": 30
    }


# Mock functions
@pytest.fixture
def mock_ml_model():
    """Mock ML model for testing."""
    class MockModel:
        def __init__(self):
            self.loaded = True
            
        def predict(self, image):
            return {
                "is_anomaly": True,
                "confidence": 0.85,
                "features": {"test": True}
            }
            
        def preprocess(self, image):
            return image
    
    return MockModel()


# Environment setup
@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    test_env = {
        "TESTING": "true",
        "JWT_SECRET": "test_secret_key",
        "LOG_LEVEL": "DEBUG",
        "METRICS_ENABLED": "false"
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)


# Cleanup fixtures
@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Cleanup after each test."""
    yield
    
    # Cleanup any test artifacts
    import gc
    gc.collect()


# Performance testing fixtures
@pytest.fixture
def performance_thresholds():
    """Performance testing thresholds."""
    return {
        "api_response_time": 1.0,  # seconds
        "image_processing_time": 10.0,  # seconds
        "database_query_time": 0.5,  # seconds
        "memory_usage_mb": 512,  # MB
    }


# Mocking utilities
class MockRabbitMQConsumer:
    """Mock RabbitMQ consumer for testing."""
    
    def __init__(self):
        self.messages = []
        self.connected = False
    
    def connect(self):
        self.connected = True
    
    def disconnect(self):
        self.connected = False
    
    def publish(self, message):
        self.messages.append(message)
    
    def consume(self):
        if self.messages:
            return self.messages.pop(0)
        return None


@pytest.fixture
def mock_rabbitmq():
    """Mock RabbitMQ for testing."""
    return MockRabbitMQConsumer()


# Database test utilities
def create_test_user(db_session, user_data):
    """Create a test user in the database."""
    from backend.auth_service.app.models import User
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    user = User(
        username=user_data["username"],
        email=user_data["email"],
        password_hash=pwd_context.hash(user_data["password"]),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        role=user_data.get("role", "operator")
    )
    
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    return user


def create_test_image(db_session, user_id, image_data=None):
    """Create a test image record in the database."""
    from backend.upload_service.app.models import Image
    import uuid
    
    if not image_data:
        image_data = {
            "filename": "test_image.jpg",
            "original_filename": "test_image.jpg",
            "file_path": "/test/path/test_image.jpg",
            "file_size": 12345,
            "mime_type": "image/jpeg",
            "checksum": "abc123def456"
        }
    
    image = Image(
        id=uuid.uuid4(),
        uploaded_by=user_id,
        **image_data
    )
    
    db_session.add(image)
    db_session.commit()
    db_session.refresh(image)
    
    return image


# Test markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )