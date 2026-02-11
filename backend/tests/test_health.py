from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test basic health check endpoint."""
    response = await client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"message": "healthy"}


@pytest.mark.asyncio
async def test_readiness_check(client: AsyncClient):
    """Test readiness check endpoint (verifies database connection)."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"message": "ready"}


@pytest.mark.asyncio
async def test_readiness_error_does_not_leak_details():
    """Test that readiness errors don't expose internal DB details."""
    # Mock the database session to raise an error with sensitive info
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=Exception("Connection refused to db.internal.corp:5432 - password auth failed")
    )

    async def failing_db():
        yield mock_session

    # Use FastAPI's dependency override mechanism
    app.dependency_overrides[get_db] = failing_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 503
            response_text = response.text.lower()
            # Should NOT contain internal details
            assert "db.internal" not in response_text
            assert "5432" not in response_text
            assert "password" not in response_text
            # Should contain generic message
            assert "not ready" in response_text
    finally:
        app.dependency_overrides.clear()
