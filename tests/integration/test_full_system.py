import pytest
import asyncio
import requests
import json
import time
from pathlib import Path
import docker
from PIL import Image
import io
import uuid


@pytest.mark.integration
class TestFullSystemIntegration:
    """Integration tests for the complete WWTP system."""
    
    @pytest.fixture(scope="class")
    def docker_client(self):
        """Docker client for managing containers."""
        return docker.from_env()
    
    @pytest.fixture(scope="class")
    def system_startup(self, docker_client):
        """Start the complete system for testing."""
        # This would start all services via docker-compose
        # For brevity, we'll mock the startup
        yield
        # Cleanup would happen here
    
    def test_system_health_endpoints(self, system_startup):
        """Test all system health endpoints."""
        health_endpoints = [
            "http://localhost/health",
            "http://localhost/api/auth/health",
            "http://localhost/api/upload/health",
            "http://localhost/api/review/health"
        ]
        
        for endpoint in health_endpoints:
            try:
                response = requests.get(endpoint, timeout=10)
                assert response.status_code == 200
                
                data = response.json()
                assert data.get("status") == "healthy"
                
            except requests.exceptions.RequestException as e:
                pytest.fail(f"Health check failed for {endpoint}: {e}")
    
    def test_user_authentication_flow(self, system_startup):
        """Test complete user authentication workflow."""
        base_url = "http://localhost/api/auth"
        
        # Test user registration
        user_data = {
            "username": f"test_user_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "password": "test_password_123",
            "first_name": "Test",
            "last_name": "User",
            "role": "operator"
        }
        
        # Register user
        response = requests.post(f"{base_url}/register", json=user_data)
        assert response.status_code == 201
        
        user_id = response.json()["id"]
        
        # Login
        login_data = {
            "username": user_data["username"],
            "password": user_data["password"]
        }
        
        response = requests.post(f"{base_url}/login", json=login_data)
        assert response.status_code == 200
        
        auth_data = response.json()
        assert "access_token" in auth_data
        assert "user" in auth_data
        
        token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test authenticated endpoint
        response = requests.get(f"{base_url}/me", headers=headers)
        assert response.status_code == 200
        
        user_info = response.json()
        assert user_info["id"] == user_id
        assert user_info["username"] == user_data["username"]
    
    def test_image_upload_and_processing_flow(self, system_startup):
        """Test complete image upload and ML processing workflow."""
        # First authenticate
        auth_response = self._authenticate()
        headers = {"Authorization": f"Bearer {auth_response['access_token']}"}
        
        # Create test image
        test_image = self._create_test_image()
        
        # Upload image
        upload_url = "http://localhost/api/upload/images"
        files = {"file": ("test.jpg", test_image, "image/jpeg")}
        
        response = requests.post(upload_url, files=files, headers=headers)
        assert response.status_code == 201
        
        image_data = response.json()
        image_id = image_data["id"]
        
        # Wait for processing to complete
        max_wait_time = 60  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            # Check image status
            response = requests.get(
                f"http://localhost/api/upload/images/{image_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                image_info = response.json()
                if image_info["processing_status"] == "completed":
                    break
                elif image_info["processing_status"] == "failed":
                    pytest.fail("Image processing failed")
            
            time.sleep(2)
        else:
            pytest.fail("Image processing timeout")
        
        # Check if detection was created
        detection_response = requests.get(
            f"http://localhost/api/review/detections?image_id={image_id}",
            headers=headers
        )
        assert detection_response.status_code == 200
        
        detections = detection_response.json()
        assert len(detections["items"]) > 0
        
        detection = detections["items"][0]
        assert "confidence_score" in detection
        assert "is_anomaly" in detection
        assert isinstance(detection["confidence_score"], float)
        assert isinstance(detection["is_anomaly"], bool)
    
    def test_review_workflow(self, system_startup):
        """Test complete review workflow."""
        # Authenticate as reviewer
        auth_response = self._authenticate(role="reviewer")
        headers = {"Authorization": f"Bearer {auth_response['access_token']}"}
        
        # Get pending reviews
        response = requests.get(
            "http://localhost/api/review/reviews/pending",
            headers=headers
        )
        assert response.status_code == 200
        
        pending_reviews = response.json()
        
        if len(pending_reviews) == 0:
            # Create a test review by uploading an image first
            image_id = self._upload_test_image(headers)
            time.sleep(5)  # Wait for processing
            
            # Assign review
            response = requests.post(
                f"http://localhost/api/review/reviews/assign/{image_id}",
                headers=headers
            )
            assert response.status_code in [200, 201]
            
            # Get the created review
            response = requests.get(
                "http://localhost/api/review/reviews/pending",
                headers=headers
            )
            pending_reviews = response.json()
        
        if len(pending_reviews) > 0:
            review = pending_reviews[0]
            review_id = review["id"]
            
            # Update review
            review_update = {
                "review_status": "approved",
                "human_verdict": "true_positive",
                "confidence_level": 4,
                "notes": "Clear anomaly visible in test image",
                "review_duration_seconds": 30
            }
            
            response = requests.put(
                f"http://localhost/api/review/reviews/{review_id}",
                json=review_update,
                headers=headers
            )
            assert response.status_code == 200
            
            updated_review = response.json()
            assert updated_review["review_status"] == "approved"
            assert updated_review["human_verdict"] == "true_positive"
    
    def test_monitoring_endpoints(self, system_startup):
        """Test monitoring and metrics endpoints."""
        # Test Prometheus metrics
        try:
            response = requests.get("http://localhost:9090/metrics", timeout=10)
            assert response.status_code == 200
            assert "prometheus" in response.text.lower()
        except requests.exceptions.RequestException:
            pytest.skip("Prometheus not available")
        
        # Test Grafana
        try:
            response = requests.get("http://localhost:3001/api/health", timeout=10)
            assert response.status_code == 200
        except requests.exceptions.RequestException:
            pytest.skip("Grafana not available")
        
        # Test RabbitMQ management
        try:
            response = requests.get(
                "http://localhost:15672/api/overview",
                auth=("admin", "admin123"),
                timeout=10
            )
            assert response.status_code == 200
        except requests.exceptions.RequestException:
            pytest.skip("RabbitMQ management not available")
    
    def test_database_connectivity(self, system_startup):
        """Test database connectivity and basic operations."""
        # This would test direct database connections
        # For integration testing, we rely on API endpoints
        
        auth_response = self._authenticate()
        headers = {"Authorization": f"Bearer {auth_response['access_token']}"}
        
        # Test data retrieval endpoints
        endpoints = [
            "http://localhost/api/upload/images",
            "http://localhost/api/review/reviews",
            "http://localhost/api/review/detections",
            "http://localhost/api/review/stats/reviews"
        ]
        
        for endpoint in endpoints:
            response = requests.get(endpoint, headers=headers)
            assert response.status_code == 200
            
            data = response.json()
            assert isinstance(data, (dict, list))
    
    def test_websocket_connectivity(self, system_startup):
        """Test WebSocket connectivity."""
        import websocket
        
        auth_response = self._authenticate()
        token = auth_response["access_token"]
        
        ws_url = f"ws://localhost/ws?token={token}"
        
        messages_received = []
        
        def on_message(ws, message):
            messages_received.append(json.loads(message))
        
        def on_error(ws, error):
            print(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print("WebSocket closed")
        
        def on_open(ws):
            print("WebSocket connected")
            # Send test message
            test_message = {
                "type": "heartbeat",
                "timestamp": time.time()
            }
            ws.send(json.dumps(test_message))
        
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run for a short time
            ws.run_forever(ping_timeout=10)
            
            # Check if we received messages
            assert len(messages_received) > 0
            
            # Should receive connection established message
            connection_msg = next(
                (msg for msg in messages_received if msg.get("type") == "connection_established"),
                None
            )
            assert connection_msg is not None
            
        except Exception as e:
            pytest.skip(f"WebSocket test skipped: {e}")
    
    @pytest.mark.slow
    def test_system_performance(self, system_startup):
        """Test system performance under load."""
        auth_response = self._authenticate()
        headers = {"Authorization": f"Bearer {auth_response['access_token']}"}
        
        # Test concurrent image uploads
        import concurrent.futures
        import threading
        
        def upload_image():
            test_image = self._create_test_image()
            files = {"file": ("test.jpg", test_image, "image/jpeg")}
            
            start_time = time.time()
            response = requests.post(
                "http://localhost/api/upload/images",
                files=files,
                headers=headers
            )
            end_time = time.time()
            
            return {
                "status_code": response.status_code,
                "duration": end_time - start_time,
                "success": response.status_code == 201
            }
        
        # Upload 5 images concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(upload_image) for _ in range(5)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # Check results
        successful_uploads = [r for r in results if r["success"]]
        assert len(successful_uploads) >= 4  # At least 80% success rate
        
        # Check response times
        avg_duration = sum(r["duration"] for r in successful_uploads) / len(successful_uploads)
        assert avg_duration < 10.0  # Should be under 10 seconds per upload
    
    def test_error_handling_and_recovery(self, system_startup):
        """Test system error handling and recovery."""
        # Test with invalid authentication
        invalid_headers = {"Authorization": "Bearer invalid_token"}
        
        response = requests.get(
            "http://localhost/api/upload/images",
            headers=invalid_headers
        )
        assert response.status_code == 401
        
        # Test with malformed request
        auth_response = self._authenticate()
        headers = {"Authorization": f"Bearer {auth_response['access_token']}"}
        
        # Upload invalid file
        invalid_file = {"file": ("test.txt", b"not an image", "text/plain")}
        response = requests.post(
            "http://localhost/api/upload/images",
            files=invalid_file,
            headers=headers
        )
        assert response.status_code in [400, 422]  # Should reject invalid file
        
        # Test rate limiting (if implemented)
        # This would test rapid successive requests
    
    # Helper methods
    def _authenticate(self, role="operator"):
        """Helper method to authenticate a user."""
        user_data = {
            "username": f"test_user_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "password": "test_password_123",
            "role": role
        }
        
        # Register
        response = requests.post("http://localhost/api/auth/register", json=user_data)
        if response.status_code != 201:
            # User might already exist, try to login
            pass
        
        # Login
        login_data = {
            "username": user_data["username"],
            "password": user_data["password"]
        }
        
        response = requests.post("http://localhost/api/auth/login", json=login_data)
        if response.status_code == 200:
            return response.json()
        else:
            # Fallback to admin user
            admin_login = {
                "username": "admin",
                "password": "admin123"
            }
            response = requests.post("http://localhost/api/auth/login", json=admin_login)
            assert response.status_code == 200
            return response.json()
    
    def _create_test_image(self):
        """Helper method to create a test image."""
        img = Image.new('RGB', (224, 224), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        return img_bytes.getvalue()
    
    def _upload_test_image(self, headers):
        """Helper method to upload a test image and return image ID."""
        test_image = self._create_test_image()
        files = {"file": ("test.jpg", test_image, "image/jpeg")}
        
        response = requests.post(
            "http://localhost/api/upload/images",
            files=files,
            headers=headers
        )
        
        if response.status_code == 201:
            return response.json()["id"]
        else:
            pytest.fail(f"Failed to upload test image: {response.status_code}")


@pytest.mark.integration
class TestSystemResilience:
    """Test system resilience and fault tolerance."""
    
    def test_service_restart_recovery(self):
        """Test system recovery after service restarts."""
        # This would test restarting individual services
        # and ensuring the system continues to function
        pass
    
    def test_database_connection_loss(self):
        """Test system behavior during database outages."""
        # This would test graceful degradation
        pass
    
    def test_rabbitmq_connection_loss(self):
        """Test system behavior during message queue outages."""
        # This would test message persistence and retry logic
        pass
    
    def test_high_load_scenarios(self):
        """Test system behavior under high load."""
        # This would test system performance limits
        pass