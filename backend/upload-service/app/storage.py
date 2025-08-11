from minio import Minio
from minio.error import S3Error
import structlog
from app.config import settings
import io
from typing import Optional

logger = structlog.get_logger()

# Initialize MinIO client
client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure
)

def ensure_bucket_exists():
    """Ensure the bucket exists, create if not"""
    try:
        if not client.bucket_exists(settings.minio_bucket_name):
            client.make_bucket(settings.minio_bucket_name)
            logger.info("Created bucket", bucket=settings.minio_bucket_name)
    except S3Error as e:
        logger.error("Error creating bucket", error=str(e))
        raise

def check_connection():
    """Check MinIO connection"""
    try:
        ensure_bucket_exists()
        return True
    except Exception as e:
        logger.error("MinIO connection failed", error=str(e))
        raise

async def store_file(filename: str, contents: bytes, content_type: str) -> str:
    """Store file in MinIO and return the file path"""
    try:
        ensure_bucket_exists()
        
        # Create file-like object from bytes
        file_data = io.BytesIO(contents)
        file_size = len(contents)
        
        # Upload to MinIO
        client.put_object(
            bucket_name=settings.minio_bucket_name,
            object_name=filename,
            data=file_data,
            length=file_size,
            content_type=content_type
        )
        
        file_path = f"{settings.minio_bucket_name}/{filename}"
        logger.info("File stored successfully", filename=filename, path=file_path)
        return file_path
        
    except S3Error as e:
        logger.error("Failed to store file", filename=filename, error=str(e))
        raise Exception(f"Failed to store file: {e}")

async def get_file(file_path: str) -> Optional[bytes]:
    """Retrieve file from MinIO"""
    try:
        # Extract filename from path
        filename = file_path.split('/')[-1]
        
        response = client.get_object(settings.minio_bucket_name, filename)
        data = response.read()
        response.close()
        response.release_conn()
        
        return data
        
    except S3Error as e:
        logger.error("Failed to retrieve file", file_path=file_path, error=str(e))
        return None

async def delete_file(file_path: str) -> bool:
    """Delete file from MinIO"""
    try:
        # Extract filename from path
        filename = file_path.split('/')[-1]
        
        client.remove_object(settings.minio_bucket_name, filename)
        logger.info("File deleted successfully", filename=filename)
        return True
        
    except S3Error as e:
        logger.error("Failed to delete file", file_path=file_path, error=str(e))
        return False

async def get_file_url(file_path: str, expires: int = 3600) -> Optional[str]:
    """Get presigned URL for file access"""
    try:
        # Extract filename from path
        filename = file_path.split('/')[-1]
        
        url = client.presigned_get_object(
            bucket_name=settings.minio_bucket_name,
            object_name=filename,
            expires=expires
        )
        
        return url
        
    except S3Error as e:
        logger.error("Failed to generate file URL", file_path=file_path, error=str(e))
        return None

def list_files(prefix: str = "") -> list:
    """List files in bucket"""
    try:
        objects = client.list_objects(settings.minio_bucket_name, prefix=prefix)
        return [obj.object_name for obj in objects]
    except S3Error as e:
        logger.error("Failed to list files", prefix=prefix, error=str(e))
        return []