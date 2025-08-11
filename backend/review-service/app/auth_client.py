import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from app.config import settings
from app.schemas import User
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AuthClient:
    def __init__(self):
        self.auth_service_url = settings.auth_service_url
        self.jwt_secret = settings.jwt_secret
        self.jwt_algorithm = settings.jwt_algorithm
    
    async def verify_token(self, token: str) -> Optional[User]:
        """Verify JWT token and return user information"""
        try:
            # First try to decode token locally
            payload = jwt.decode(
                token, 
                self.jwt_secret, 
                algorithms=[self.jwt_algorithm]
            )
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            
            # Get user details from auth service
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.auth_service_url}/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    return User(**user_data)
                else:
                    logger.warning(f"Auth service returned {response.status_code}")
                    return None
                    
        except JWTError as e:
            logger.warning(f"JWT decode error: {e}")
            return None
        except httpx.TimeoutException:
            logger.error("Auth service timeout")
            return None
        except httpx.RequestError as e:
            logger.error(f"Auth service request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected auth error: {e}")
            return None
    
    async def check_permission(self, user: User, action: str, resource: str = None) -> bool:
        """Check if user has permission for specific action"""
        try:
            # Basic role-based permissions
            if user.role == "admin":
                return True
            
            if user.role == "reviewer" and action in ["read", "review", "update_review"]:
                return True
            
            if user.role == "operator" and action in ["read", "upload"]:
                return True
            
            # For more complex permissions, call auth service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.auth_service_url}/auth/check-permission",
                    json={
                        "user_id": str(user.id),
                        "action": action,
                        "resource": resource
                    },
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("allowed", False)
                else:
                    # Fallback to basic role check
                    return user.role == "admin"
                    
        except Exception as e:
            logger.error(f"Permission check error: {e}")
            # Conservative fallback - only allow admins when service is unavailable
            return user.role == "admin"


# Global auth client instance
auth_client = AuthClient()


async def get_current_user(token: str) -> User:
    """Dependency to get current authenticated user"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await auth_client.verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user


async def require_permission(user: User, action: str, resource: str = None):
    """Check if user has required permission, raise exception if not"""
    has_permission = await auth_client.check_permission(user, action, resource)
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for action: {action}"
        )