import pytest
from httpx import AsyncClient


@pytest.fixture
async def project_with_key(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a project and return its details including API key."""
    response = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Event Test Project"},
    )
    return response.json()


@pytest.mark.asyncio
async def test_ingest_single_event(client: AsyncClient, project_with_key: dict):
    """Test ingesting a single event."""
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": project_with_key["api_key"]},
        json={
            "events": [
                {
                    "event": "page_view",
                    "properties": {"path": "/home"},
                    "session_id": "sess_123",
                    "page_url": "https://example.com/home",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_ingest_batch_events(client: AsyncClient, project_with_key: dict):
    """Test ingesting a batch of events."""
    events = [
        {"event": "page_view", "session_id": "sess_1", "page_url": "https://example.com/"},
        {"event": "button_click", "session_id": "sess_1", "properties": {"button": "signup"}},
        {"event": "page_view", "session_id": "sess_2", "page_url": "https://example.com/pricing"},
    ]
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": project_with_key["api_key"]},
        json={"events": events},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 3


@pytest.mark.asyncio
async def test_ingest_with_invalid_api_key(client: AsyncClient):
    """Test ingesting events with an invalid API key."""
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": "invalid_key"},
        json={"events": [{"event": "page_view"}]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_without_api_key(client: AsyncClient):
    """Test ingesting events without an API key."""
    response = await client.post(
        "/api/v1/events/ingest",
        json={"events": [{"event": "page_view"}]},
    )
    assert response.status_code == 422  # Missing required header


@pytest.mark.asyncio
async def test_ingest_empty_events(client: AsyncClient, project_with_key: dict):
    """Test ingesting an empty events array fails validation."""
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": project_with_key["api_key"]},
        json={"events": []},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_with_distinct_id(client: AsyncClient, project_with_key: dict):
    """Test ingesting events with user identification."""
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": project_with_key["api_key"]},
        json={
            "events": [
                {
                    "event": "purchase",
                    "distinct_id": "user_42",
                    "properties": {"amount": 29.99, "plan": "pro"},
                    "session_id": "sess_abc",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_ingest_with_timestamp(client: AsyncClient, project_with_key: dict):
    """Test ingesting events with custom timestamps."""
    response = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": project_with_key["api_key"]},
        json={
            "events": [
                {
                    "event": "page_view",
                    "timestamp": "2026-02-10T12:00:00Z",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] == 1
