import os
from typing import TYPE_CHECKING, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test env vars before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-must-be-at-least-32-characters-long"
os.environ["REDIS_URL"] = "memory://"


class AsyncIterator:
    """Async iterator for mocking redis.scan_iter."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration as err:
            raise StopAsyncIteration from err


# Stateful Redis mock for proper token tracking
class FakeRedisStore:
    """Stateful fake Redis for testing token storage/revocation."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def clear(self):
        self.store.clear()

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                count += 1
        return count

    def scan_iter(self, pattern: str):
        import fnmatch

        matching = [k for k in self.store.keys() if fnmatch.fnmatch(k, pattern)]
        return AsyncIterator(matching)

    async def close(self):
        pass


_fake_redis_store = FakeRedisStore()

# Create a fake redis client that delegates to the store
_fake_redis_client = MagicMock()
_fake_redis_client.setex = AsyncMock(side_effect=_fake_redis_store.setex)
_fake_redis_client.get = AsyncMock(side_effect=_fake_redis_store.get)
_fake_redis_client.exists = AsyncMock(side_effect=_fake_redis_store.exists)
_fake_redis_client.delete = AsyncMock(side_effect=_fake_redis_store.delete)
_fake_redis_client.scan_iter = MagicMock(side_effect=_fake_redis_store.scan_iter)
_fake_redis_client.close = AsyncMock(side_effect=_fake_redis_store.close)


async def _mock_get_redis():
    return _fake_redis_client


# Patch Redis at the module level before any imports
_redis_patcher = patch("app.core.redis.get_redis", _mock_get_redis)
_redis_patcher.start()

# Also patch where it's imported in security.py
patch("app.core.security.get_redis", _mock_get_redis).start()

# Test database URL (use SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Type checking imports only (for IDE support without importing at runtime)
if TYPE_CHECKING:
    pass


@pytest.fixture(autouse=True)
async def setup_database():
    from app.db.base import Base

    # Clear Redis store for each test
    _fake_redis_store.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user for authenticated tests."""
    from app.schemas.user import UserCreate
    from app.services.user_service import UserService

    service = UserService(db_session)
    user_data = UserCreate(
        email="testuser@example.com",
        password="TestPassword123!",  # Meets new password policy
        full_name="Test User",
    )
    user = await service.create(user_data)
    await db_session.commit()
    return user


@pytest.fixture
async def auth_headers(test_user) -> dict:
    """Get auth headers for authenticated requests."""
    from app.core.config import settings
    from app.core.security import create_access_token, store_access_token

    token, jti = create_access_token(subject=test_user.id)
    # Store the access token in Redis so it passes revocation check
    await store_access_token(
        user_id=test_user.id,
        jti=jti,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def superuser(db_session: AsyncSession):
    """Create a superuser for admin tests."""
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        email="admin@example.com",
        hashed_password=hash_password("AdminPassword123!"),  # Meets new password policy
        full_name="Admin User",
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    await db_session.commit()
    return user


@pytest.fixture
async def superuser_headers(superuser) -> dict:
    """Get auth headers for superuser requests."""
    from app.core.config import settings
    from app.core.security import create_access_token, store_access_token

    token, jti = create_access_token(subject=superuser.id)
    # Store the access token in Redis so it passes revocation check
    await store_access_token(
        user_id=superuser.id,
        jti=jti,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"Authorization": f"Bearer {token}"}
