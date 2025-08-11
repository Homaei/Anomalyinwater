from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import structlog
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
import time
from typing import Optional

from app.database import get_db, engine
from app import models, schemas, crud, auth
from app.config import settings

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WWTP Auth Service",
    description="Authentication and authorization service for WWTP Anomaly Detection",
    version="1.0.0"
)

security = HTTPBearer()
logger = structlog.get_logger()

# Prometheus metrics
REQUEST_COUNT = Counter('auth_requests_total', 'Total auth requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('auth_request_duration_seconds', 'Request duration')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    REQUEST_DURATION.observe(duration)
    
    return response

@app.get("/")
async def root():
    return {"message": "WWTP Auth Service", "version": "1.0.0"}

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/auth/register", response_model=schemas.User)
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username already taken"
        )
    
    logger.info("Creating new user", username=user.username, email=user.email)
    return crud.create_user(db=db, user=user)

@app.post("/auth/login", response_model=schemas.Token)
async def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = crud.authenticate_user(db, user_credentials.username, user_credentials.password)
    if not user:
        logger.warning("Failed login attempt", username=user_credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth.create_access_token(data={"sub": user.username, "user_id": str(user.id), "role": user.role})
    
    # Update last login
    crud.update_user_last_login(db, user.id)
    
    logger.info("Successful login", username=user.username, user_id=str(user.id))
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@app.post("/auth/refresh", response_model=schemas.Token)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = auth.verify_token(credentials.credentials)
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = crud.get_user_by_username(db, username)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        new_token = auth.create_access_token(
            data={"sub": user.username, "user_id": str(user.id), "role": user.role}
        )
        return {"access_token": new_token, "token_type": "bearer"}
    except Exception as e:
        logger.error("Token refresh failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/auth/users", response_model=list[schemas.User])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(auth.get_current_admin_user),
    db: Session = Depends(get_db)
):
    users = crud.get_users(db, skip=skip, limit=limit)
    return users

@app.put("/auth/users/{user_id}", response_model=schemas.User)
async def update_user(
    user_id: str,
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(auth.get_current_admin_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = crud.update_user(db, user_id, user_update)
    logger.info("User updated", user_id=user_id, updated_by=current_user.username)
    return updated_user

@app.delete("/auth/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: models.User = Depends(auth.get_current_admin_user),
    db: Session = Depends(get_db)
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    crud.delete_user(db, user_id)
    logger.info("User deleted", user_id=user_id, deleted_by=current_user.username)
    return {"message": "User deleted successfully"}

@app.post("/auth/verify-token")
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    try:
        payload = auth.verify_token(credentials.credentials)
        username = payload.get("sub")
        user_id = payload.get("user_id")
        role = payload.get("role")
        
        if not all([username, user_id, role]):
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        user = crud.get_user(db, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")
        
        return {
            "valid": True,
            "user_id": user_id,
            "username": username,
            "role": role,
            "email": user.email
        }
    except Exception as e:
        logger.error("Token verification failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")