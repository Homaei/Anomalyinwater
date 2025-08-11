from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set, Optional
from uuid import UUID
import json
import asyncio
import logging
from datetime import datetime
from app.schemas import WebSocketMessage, NotificationMessage, User
from app.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # Store active connections by user_id
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        # Store user info for each connection
        self.connection_users: Dict[WebSocket, User] = {}
        # Store connection metadata
        self.connection_metadata: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket, user: User):
        """Accept websocket connection and register user"""
        await websocket.accept()
        
        # Initialize user connections if not exists
        if user.id not in self.active_connections:
            self.active_connections[user.id] = set()
        
        # Add connection
        self.active_connections[user.id].add(websocket)
        self.connection_users[websocket] = user
        self.connection_metadata[websocket] = {
            "connected_at": datetime.now(),
            "last_heartbeat": datetime.now()
        }
        
        logger.info(f"WebSocket connected for user {user.username} ({user.id})")
        
        # Send welcome message
        await self.send_personal_message({
            "type": "connection_established",
            "data": {
                "user_id": str(user.id),
                "username": user.username,
                "connected_at": datetime.now().isoformat()
            }
        }, websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove websocket connection"""
        user = self.connection_users.get(websocket)
        if user and user.id in self.active_connections:
            self.active_connections[user.id].discard(websocket)
            
            # Clean up empty user connections
            if not self.active_connections[user.id]:
                del self.active_connections[user.id]
        
        # Clean up metadata
        self.connection_users.pop(websocket, None)
        self.connection_metadata.pop(websocket, None)
        
        if user:
            logger.info(f"WebSocket disconnected for user {user.username} ({user.id})")
    
    async def send_personal_message(self, message: Dict, websocket: WebSocket):
        """Send message to specific websocket connection"""
        try:
            ws_message = WebSocketMessage(
                type=message["type"],
                data=message["data"],
                timestamp=datetime.now()
            )
            await websocket.send_text(ws_message.model_dump_json())
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            self.disconnect(websocket)
    
    async def send_user_message(self, message: Dict, user_id: UUID):
        """Send message to all connections for a specific user"""
        if user_id not in self.active_connections:
            return
        
        # Send to all user's connections
        disconnected_connections = set()
        for websocket in self.active_connections[user_id].copy():
            try:
                await self.send_personal_message(message, websocket)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                disconnected_connections.add(websocket)
        
        # Clean up disconnected connections
        for websocket in disconnected_connections:
            self.disconnect(websocket)
    
    async def send_role_message(self, message: Dict, role: str):
        """Send message to all users with specific role"""
        for user_id, connections in self.active_connections.items():
            # Get user from any connection (they should all be the same user)
            if connections:
                websocket = next(iter(connections))
                user = self.connection_users.get(websocket)
                if user and user.role == role:
                    await self.send_user_message(message, user_id)
    
    async def broadcast_message(self, message: Dict):
        """Send message to all connected users"""
        for user_id in list(self.active_connections.keys()):
            await self.send_user_message(message, user_id)
    
    async def send_notification(self, notification: NotificationMessage):
        """Send notification to specific user or broadcast"""
        message = {
            "type": "notification",
            "data": {
                "message": notification.message,
                "severity": notification.severity,
                "data": notification.data
            }
        }
        
        if notification.user_id:
            await self.send_user_message(message, notification.user_id)
        else:
            await self.broadcast_message(message)
    
    def get_connected_users(self) -> List[Dict]:
        """Get list of currently connected users"""
        users = []
        for user_id, connections in self.active_connections.items():
            if connections:
                # Get user from first connection
                websocket = next(iter(connections))
                user = self.connection_users.get(websocket)
                metadata = self.connection_metadata.get(websocket, {})
                
                if user:
                    users.append({
                        "user_id": str(user.id),
                        "username": user.username,
                        "role": user.role,
                        "connection_count": len(connections),
                        "connected_at": metadata.get("connected_at"),
                        "last_heartbeat": metadata.get("last_heartbeat")
                    })
        
        return users
    
    async def handle_heartbeat(self, websocket: WebSocket):
        """Handle heartbeat from client"""
        if websocket in self.connection_metadata:
            self.connection_metadata[websocket]["last_heartbeat"] = datetime.now()
            
            await self.send_personal_message({
                "type": "heartbeat_ack",
                "data": {"timestamp": datetime.now().isoformat()}
            }, websocket)
    
    async def cleanup_stale_connections(self):
        """Clean up stale connections that haven't sent heartbeat"""
        heartbeat_timeout = settings.websocket_heartbeat_interval * 2  # 2x interval
        cutoff_time = datetime.now().timestamp() - heartbeat_timeout
        
        stale_connections = []
        for websocket, metadata in self.connection_metadata.items():
            last_heartbeat = metadata.get("last_heartbeat", datetime.now())
            if last_heartbeat.timestamp() < cutoff_time:
                stale_connections.append(websocket)
        
        for websocket in stale_connections:
            logger.warning("Cleaning up stale WebSocket connection")
            self.disconnect(websocket)
            try:
                await websocket.close(code=1000, reason="Heartbeat timeout")
            except:
                pass


class NotificationService:
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
    
    async def notify_new_detection(self, detection_id: UUID, is_anomaly: bool, confidence: float):
        """Notify reviewers about new detection"""
        message = {
            "type": "new_detection",
            "data": {
                "detection_id": str(detection_id),
                "is_anomaly": is_anomaly,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Notify reviewers and admins
        await self.connection_manager.send_role_message(message, "reviewer")
        await self.connection_manager.send_role_message(message, "admin")
    
    async def notify_review_completed(self, review_id: UUID, detection_id: UUID, verdict: str):
        """Notify about completed review"""
        message = {
            "type": "review_completed",
            "data": {
                "review_id": str(review_id),
                "detection_id": str(detection_id),
                "verdict": verdict,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # Broadcast to all users
        await self.connection_manager.broadcast_message(message)
    
    async def notify_system_alert(self, alert_type: str, message: str, data: Dict = None):
        """Send system alert notification"""
        notification = NotificationMessage(
            message=message,
            severity="warning",
            data={"alert_type": alert_type, **(data or {})}
        )
        
        # Send to admins only
        await self.connection_manager.send_role_message({
            "type": "system_alert",
            "data": {
                "alert_type": alert_type,
                "message": message,
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            }
        }, "admin")


# Global manager instances
manager = ConnectionManager()
notification_service = NotificationService(manager)


async def periodic_cleanup():
    """Periodic task to clean up stale connections"""
    while True:
        try:
            await manager.cleanup_stale_connections()
            await asyncio.sleep(settings.websocket_heartbeat_interval)
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
            await asyncio.sleep(60)  # Wait longer on error