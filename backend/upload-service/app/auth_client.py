import httpx
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog
from app.config import settings

logger = structlog.get_logger()
security = HTTPBearer()

async def verify_token_with_auth_service(token: str) -> dict:
    """Verify token with auth service"""
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.post(
                f"{settings.auth_service_url}/auth/verify-token",
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning("Token verification failed", status_code=response.status_code)
                raise HTTPException(status_code=401, detail="Invalid token")
                
    except httpx.RequestError as e:
        logger.error("Auth service connection failed", error=str(e))
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    except Exception as e:
        logger.error("Token verification error", error=str(e))
        raise HTTPException(status_code=401, detail="Token verification failed")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current user from token"""
    token_data = await verify_token_with_auth_service(credentials.credentials)
    if not token_data.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return {
        "user_id": token_data["user_id"],
        "username": token_data["username"],
        "role": token_data["role"],
        "email": token_data["email"]
    }

async def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Get current admin user"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user