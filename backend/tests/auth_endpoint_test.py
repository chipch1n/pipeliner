from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth import (
    hash_password,
)
from backend.app.db import get_db
from backend.app.main import (
    app,
    get_current_user,
)
from backend.tests.util.db_util import setup_mock_execute

mocked_db = AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_db():
    mocked_db.reset_mock()
    return mocked_db

@pytest.fixture
def test_client():
    async def override_get_db():
        return mocked_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

class TestAuthEndpoints:
    def test_register_success(self, test_client, mock_db):
        setup_mock_execute(mock_db, None)

        response = test_client.post("/register", json={"username": "testuser", "password": "secret123"})

        assert response.status_code == 201
        assert response.json() == {"username": "testuser"}
        mock_db.commit.assert_called()

    def test_register_existing(self, test_client, mock_db):
        setup_mock_execute(mock_db, MagicMock())

        response = test_client.post("/register", json={"username": "testuser", "password": "secret123"})

        assert response.status_code == 400

    def test_login_success(self, test_client, mock_db):
        user = MagicMock()
        user.username = "loginuser"
        user.id = 1
        user.password_hash = hash_password("correctpass")
        user.lockout_until = None
        user.failed_attempts = 0
        setup_mock_execute(mock_db, user)

        response = test_client.post("/login", json={"username": "loginuser", "password": "correctpass"})

        assert response.status_code == 200
        assert response.json() == {"username": "loginuser"}
        cookies = response.headers.get("set-cookie", "")
        assert "session_token=" in cookies

    def test_login_locked(self, test_client, mock_db):
        user = MagicMock()
        user.username = "lockeduser"
        user.password_hash = hash_password("anypass")
        user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        user.failed_attempts = 3
        setup_mock_execute(mock_db, user)

        response = test_client.post("/login", json={"username": "lockeduser", "password": "anypass"})

        assert response.status_code == 423
        assert response.json() == {"detail": f"Account locked. Try again after {user.lockout_until.strftime('%Y-%m-%d %H:%M:%S')} UTC."}

    def test_logout(self, test_client, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        async def mock_execute(*args, **kwargs):
            return mock_result
        mock_db.execute = mock_execute
        test_client.cookies["session_token"] = "valid_token"

        response = test_client.post("/logout")

        assert response.status_code == 200
        assert response.json() == {"message": "Logged out successfully"}

    def test_logout_without_token(self, test_client):
        response = test_client.post("/logout")
        assert response.status_code == 400
        assert response.json() == {"detail": "Already logged out"}

    def test_user_info_unauthorized(self, test_client):
        response = test_client.get("/user-info")
        assert response.status_code == 401

    def test_user_info_authorized(self, test_client):
        async def mock_get_current_user(request=None, db=None):
            return 42
        app.dependency_overrides[get_current_user] = mock_get_current_user

        response = test_client.get("/user-info")
        assert response.status_code == 200
        assert response.json() == {"user_id": 42}