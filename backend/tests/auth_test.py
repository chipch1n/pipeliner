import io
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth import (
    hash_password,
    verify_password,
    create_user,
    authenticate_user,
    generate_session_token,
    create_session,
    delete_session,
    validate_session_token,
)
from backend.app.db import get_db
from backend.app.main import (
    app,
)
from backend.tests.util.db_util import setup_mock_execute

mocked_db = AsyncMock(spec=AsyncSession)

@pytest.fixture
def mock_db():
    mocked_db.reset_mock()
    return mocked_db

@pytest.fixture
def test_image():
    img = Image.new("RGB", (10, 10), color="red")
    return img

@pytest.fixture
def test_image_bytes(test_image):
    buf = io.BytesIO()
    test_image.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

@pytest.fixture
def test_client():
    async def override_get_db():
        return mocked_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

class TestAuth:
    def test_hash_password_consistency(self):
        pwd = "mysecret"
        h1 = hash_password(pwd)
        h2 = hash_password(pwd)
        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 64

    def test_verify_password(self):
        pwd = "password123"
        hashed = hash_password(pwd)
        assert verify_password(pwd, hashed) is True
        assert verify_password("wrong", hashed) is False

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_db):
        setup_mock_execute(mock_db, None)

        user = await create_user(mock_db, "newuser", "pass")

        assert user is not None
        assert user.username == "newuser"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_existing(self, mock_db):
        existing_user = MagicMock()
        setup_mock_execute(mock_db, existing_user)

        user = await create_user(mock_db, "existing", "pass")

        assert user is None
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, mock_db):
        user = MagicMock()
        user.username = "test"
        user.password_hash = hash_password("test")
        user.lockout_until = None
        user.failed_attempts = 0
        setup_mock_execute(mock_db, user)

        result = await authenticate_user(mock_db, "test", "test")

        assert result == user
        assert user.failed_attempts == 0
        assert user.lockout_until is None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_authenticate_user_locked(self, mock_db):
        user = MagicMock()
        user.username = "locked"
        user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        user.failed_attempts = 3
        setup_mock_execute(mock_db, user)

        with pytest.raises(Exception) as exc_info:
            await authenticate_user(mock_db, "locked", "bad")

        assert exc_info.value.status_code == 423

    @pytest.mark.asyncio
    async def test_authenticate_user_lockout_expired(self, mock_db):
        user = MagicMock()
        user.username = "expired"
        user.lockout_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        user.failed_attempts = 3
        setup_mock_execute(mock_db, user)

        with pytest.raises(Exception) as exc_info:
            await authenticate_user(mock_db, "expired", "bad")

        assert user.lockout_until is None
        assert user.failed_attempts == 1
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, mock_db):
        user = MagicMock()
        user.username = "test"
        user.password_hash = hash_password("test")
        user.lockout_until = None
        user.failed_attempts = 0
        setup_mock_execute(mock_db, user)

        with pytest.raises(Exception) as exc_info:
            await authenticate_user(mock_db, "test", "wrong")

        assert user.failed_attempts == 1
        assert exc_info.value.status_code == 401

    def test_generate_session_token_length(self):
        token = generate_session_token()
        assert len(token) == 86

    @pytest.mark.asyncio
    async def test_create_session(self, mock_db):
        user_id = 42
        test_token = "testtoken"

        with patch("secrets.token_urlsafe", return_value=test_token):
            token = await create_session(mock_db, user_id)

        assert token == test_token
        mock_db.add.assert_called_once()
        session_arg = mock_db.add.call_args[0][0]
        assert session_arg.token == test_token
        assert session_arg.user_id == user_id
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_validate_session(self, mock_db):
        user_id = 42
        setup_mock_execute(mock_db, user_id)

        userid = await validate_session_token(mock_db, 'testtoken')
        assert userid == user_id

    @pytest.mark.asyncio
    async def test_delete_session(self, mock_db):
        mocked_db.execute = AsyncMock()
        mock_db.execute.return_value.rowcount = 1

        result = await delete_session(mock_db, 'anytoken')

        assert result is True
        mock_db.commit.assert_called()