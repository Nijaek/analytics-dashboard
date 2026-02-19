import os
from typing import TYPE_CHECKING, AsyncGenerator
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test env vars before importing app modules
os.environ["SECRET_KEY"] = "test-secret-key-must-be-at-least-32-characters-long"
os.environ["REDIS_URL"] = "memory://"
os.environ["COOKIE_SECURE"] = "false"  # httpx test client uses http://, not https://

# Shared FakeServer holds state; each call creates a fresh client
# bound to the current event loop (avoids pytest-asyncio loop mismatch).
_fake_server = fakeredis.FakeServer()


async def _mock_get_redis():
    return fakeredis.aioredis.FakeRedis(server=_fake_server, decode_responses=True)


# Patch the module-level get_redis() used as fallback in non-DI contexts
_redis_patcher = patch("app.core.redis.get_redis", _mock_get_redis)
_redis_patcher.start()


# Patch stream's fallback path (stream functions fall back to get_redis when no
# redis kwarg is passed — this keeps stream ops unavailable by default in tests)
async def _mock_stream_get_redis_unavailable():
    """Simulate Redis unavailable for stream operations.

    Most tests need events written to Postgres (via fallback), not the stream.
    Stream-specific tests can override this by patching app.core.stream.get_redis
    with _mock_get_redis locally.
    """
    raise ConnectionError("Redis stream not available in tests")


patch("app.core.stream.get_redis", _mock_stream_get_redis_unavailable).start()

# Test database URL (use SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Type checking imports only (for IDE support without importing at runtime)
if TYPE_CHECKING:
    pass


def _make_fake_redis():
    """Create a fakeredis instance bound to the shared server."""
    return fakeredis.aioredis.FakeRedis(server=_fake_server, decode_responses=True)


@pytest.fixture(autouse=True)
async def setup_database():
    from app.core.limiter import limiter
    from app.db.base import Base

    # Disable rate limiting in tests — limits are tested explicitly where needed
    limiter.enabled = False

    # Clear fakeredis for each test
    r = fakeredis.aioredis.FakeRedis(server=_fake_server, decode_responses=True)
    await r.flushall()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def fake_redis():
    """Provide a fakeredis instance for direct use in tests."""
    return _make_fake_redis()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.core.redis import get_redis_dep
    from app.db.session import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    async def override_get_redis_dep():
        return _make_fake_redis()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_dep] = override_get_redis_dep

    # Also set app.state.redis for WebSocket handler (which reads it directly)
    app.state.redis = _make_fake_redis()

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
    # store_access_token uses redis kwarg; when None it falls back to
    # the patched get_redis() which returns fakeredis.
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
    # Falls back to patched get_redis() for fakeredis
    await store_access_token(
        user_id=superuser.id,
        jti=jti,
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"Authorization": f"Bearer {token}"}
