import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timedelta


# Auth service tests
class TestAuthService:
    """Test suite for authentication service."""
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session, test_user_data, test_admin_user_data):
        """Set up test data."""
        self.db = db_session
        self.user_data = test_user_data
        self.admin_data = test_admin_user_data
    
    def test_register_user_success(self):
        """Test successful user registration."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            # Mock database session
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                response = client.post("/register", json=self.user_data)
                
                assert response.status_code == 201
                data = response.json()
                assert "id" in data
                assert data["username"] == self.user_data["username"]
                assert data["email"] == self.user_data["email"]
                assert "password_hash" not in data  # Should not expose password hash
    
    def test_register_user_duplicate_username(self):
        """Test registration with duplicate username."""
        from tests.backend.conftest import create_test_user
        
        # Create user first
        create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                response = client.post("/register", json=self.user_data)
                
                assert response.status_code == 400
                assert "already exists" in response.json()["detail"]
    
    def test_login_success(self):
        """Test successful login."""
        from tests.backend.conftest import create_test_user
        
        # Create user first
        user = create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                login_data = {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"]
                }
                
                response = client.post("/login", json=login_data)
                
                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "token_type" in data
                assert "user" in data
                assert data["user"]["username"] == self.user_data["username"]
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                login_data = {
                    "username": "nonexistent",
                    "password": "wrongpassword"
                }
                
                response = client.post("/login", json=login_data)
                
                assert response.status_code == 401
                assert "Invalid credentials" in response.json()["detail"]
    
    def test_get_current_user_success(self, mock_jwt_token, auth_headers):
        """Test getting current user with valid token."""
        from tests.backend.conftest import create_test_user
        
        user = create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                # Mock JWT decode
                with patch('backend.auth_service.app.auth.jwt.decode') as mock_decode:
                    mock_decode.return_value = {"sub": str(user.id)}
                    
                    response = client.get("/me", headers=auth_headers)
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["username"] == self.user_data["username"]
    
    def test_get_current_user_invalid_token(self):
        """Test getting current user with invalid token."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            invalid_headers = {"Authorization": "Bearer invalid_token"}
            
            response = client.get("/me", headers=invalid_headers)
            
            assert response.status_code == 401
    
    def test_refresh_token_success(self, mock_jwt_token, auth_headers):
        """Test token refresh."""
        from tests.backend.conftest import create_test_user
        
        user = create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                with patch('backend.auth_service.app.auth.jwt.decode') as mock_decode:
                    mock_decode.return_value = {"sub": str(user.id)}
                    
                    response = client.post("/refresh", headers=auth_headers)
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert "access_token" in data
    
    def test_logout_success(self, auth_headers):
        """Test successful logout."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            response = client.post("/logout", headers=auth_headers)
            
            assert response.status_code == 200
    
    def test_change_password_success(self, mock_jwt_token, auth_headers):
        """Test successful password change."""
        from tests.backend.conftest import create_test_user
        
        user = create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                with patch('backend.auth_service.app.auth.jwt.decode') as mock_decode:
                    mock_decode.return_value = {"sub": str(user.id)}
                    
                    password_data = {
                        "current_password": self.user_data["password"],
                        "new_password": "newpassword123"
                    }
                    
                    response = client.put("/change-password", json=password_data, headers=auth_headers)
                    
                    assert response.status_code == 200
    
    def test_admin_get_users(self, mock_jwt_token):
        """Test admin getting list of users."""
        from tests.backend.conftest import create_test_user
        
        # Create admin user
        admin_user = create_test_user(self.db, self.admin_data)
        create_test_user(self.db, self.user_data)  # Regular user
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                with patch('backend.auth_service.app.auth.jwt.decode') as mock_decode:
                    mock_decode.return_value = {"sub": str(admin_user.id)}
                    
                    admin_headers = {"Authorization": f"Bearer {mock_jwt_token}"}
                    response = client.get("/users", headers=admin_headers)
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert "items" in data
                    assert len(data["items"]) >= 2  # Admin + regular user
    
    @pytest.mark.performance
    def test_login_performance(self, performance_thresholds):
        """Test login performance."""
        from tests.backend.conftest import create_test_user
        import time
        
        user = create_test_user(self.db, self.user_data)
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            with patch('backend.auth_service.app.main.get_db') as mock_get_db:
                mock_get_db.return_value = self.db
                
                login_data = {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"]
                }
                
                start_time = time.time()
                response = client.post("/login", json=login_data)
                end_time = time.time()
                
                assert response.status_code == 200
                assert (end_time - start_time) < performance_thresholds["api_response_time"]
    
    def test_rate_limiting(self):
        """Test rate limiting on login endpoint."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            # Attempt multiple rapid requests
            login_data = {
                "username": "test",
                "password": "wrong"
            }
            
            responses = []
            for _ in range(10):  # Exceed rate limit
                response = client.post("/login", json=login_data)
                responses.append(response.status_code)
            
            # Should get rate limited after several attempts
            assert 429 in responses
    
    def test_jwt_token_expiry(self):
        """Test JWT token expiry handling."""
        from jose import jwt
        from datetime import datetime, timedelta
        
        # Create expired token
        expired_payload = {
            "sub": "testuser",
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        
        expired_token = jwt.encode(expired_payload, "test_secret_key", algorithm="HS256")
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            expired_headers = {"Authorization": f"Bearer {expired_token}"}
            response = client.get("/me", headers=expired_headers)
            
            assert response.status_code == 401
            assert "expired" in response.json()["detail"].lower()


# Integration tests
@pytest.mark.integration
class TestAuthServiceIntegration:
    """Integration tests for auth service."""
    
    def test_full_auth_flow(self, db_session, test_user_data):
        """Test complete authentication flow."""
        # This would test the full flow with real database and services
        pass
    
    def test_auth_with_external_services(self):
        """Test authentication with external services."""
        # Test integration with Redis, database, etc.
        pass


# Security tests
class TestAuthSecurity:
    """Security tests for authentication."""
    
    def test_password_hashing(self, test_user_data):
        """Test password is properly hashed."""
        from backend.auth_service.app.auth import get_password_hash, verify_password
        
        password = test_user_data["password"]
        hashed = get_password_hash(password)
        
        # Password should be hashed
        assert hashed != password
        assert len(hashed) > len(password)
        
        # Should be verifiable
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)
    
    def test_sql_injection_protection(self):
        """Test protection against SQL injection."""
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            # Attempt SQL injection
            malicious_data = {
                "username": "admin'; DROP TABLE users; --",
                "password": "password"
            }
            
            response = client.post("/login", json=malicious_data)
            
            # Should handle gracefully without exposing database errors
            assert response.status_code in [400, 401, 422]
    
    def test_xss_protection(self):
        """Test XSS protection in user data."""
        xss_data = {
            "username": "<script>alert('xss')</script>",
            "email": "test@example.com",
            "password": "password123",
            "first_name": "<img src=x onerror=alert('xss')>",
            "last_name": "User"
        }
        
        with patch('backend.auth_service.app.main.app') as mock_app:
            client = TestClient(mock_app)
            
            response = client.post("/register", json=xss_data)
            
            if response.status_code == 201:
                # If creation succeeded, ensure XSS is escaped
                data = response.json()
                assert "<script>" not in str(data)
                assert "onerror=" not in str(data)