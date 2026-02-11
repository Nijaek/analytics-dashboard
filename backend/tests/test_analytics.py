from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.user import User


@pytest.fixture
async def project_with_events(
    client: AsyncClient, auth_headers: dict, test_user: User, db_session: AsyncSession
) -> dict:
    """Create a project with sample events for analytics testing."""
    # Create project
    resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Analytics Project"},
    )
    project_data = resp.json()
    project_id = project_data["id"]

    # Insert events directly for test control
    now = datetime.now(timezone.utc)
    events = [
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_1",
            distinct_id="user_1",
            page_url="https://example.com/",
            timestamp=now - timedelta(hours=2),
        ),
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_1",
            distinct_id="user_1",
            page_url="https://example.com/pricing",
            timestamp=now - timedelta(hours=1),
        ),
        Event(
            project_id=project_id,
            event_name="button_click",
            session_id="sess_1",
            distinct_id="user_1",
            properties={"button": "signup"},
            timestamp=now - timedelta(minutes=30),
        ),
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_2",
            distinct_id="user_2",
            page_url="https://example.com/",
            timestamp=now - timedelta(minutes=15),
        ),
        Event(
            project_id=project_id,
            event_name="signup",
            session_id="sess_2",
            distinct_id="user_2",
            timestamp=now - timedelta(minutes=5),
        ),
    ]
    for event in events:
        db_session.add(event)
    await db_session.flush()
    await db_session.commit()

    return project_data


@pytest.mark.asyncio
async def test_overview(client: AsyncClient, auth_headers: dict, project_with_events: dict):
    """Test overview metrics endpoint."""
    project_id = project_with_events["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 5
    assert data["unique_sessions"] == 2
    assert data["unique_users"] == 2
    assert data["top_event"] == "page_view"


@pytest.mark.asyncio
async def test_overview_unauthenticated(client: AsyncClient, project_with_events: dict):
    """Test overview requires authentication."""
    project_id = project_with_events["id"]
    response = await client.get(f"/api/v1/analytics/{project_id}/overview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_timeseries(client: AsyncClient, auth_headers: dict, project_with_events: dict):
    """Test timeseries endpoint."""
    project_id = project_with_events["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/timeseries?period=24h&granularity=hourly",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "hourly"
    assert len(data["data"]) > 0
    # Each point has timestamp and count
    point = data["data"][0]
    assert "timestamp" in point
    assert "count" in point


@pytest.mark.asyncio
async def test_top_events(client: AsyncClient, auth_headers: dict, project_with_events: dict):
    """Test top events endpoint."""
    project_id = project_with_events["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/top-events?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 3  # page_view, button_click, signup
    # page_view should be first (3 events)
    assert data[0]["event_name"] == "page_view"
    assert data[0]["count"] == 3


@pytest.mark.asyncio
async def test_sessions(client: AsyncClient, auth_headers: dict, project_with_events: dict):
    """Test sessions endpoint."""
    project_id = project_with_events["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/sessions?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["data"]) == 2


@pytest.mark.asyncio
async def test_users_analytics(client: AsyncClient, auth_headers: dict, project_with_events: dict):
    """Test users analytics endpoint."""
    project_id = project_with_events["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/users?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["data"]) == 2


@pytest.mark.asyncio
async def test_analytics_wrong_project(
    client: AsyncClient, auth_headers: dict, superuser: User, superuser_headers: dict
):
    """Test accessing analytics for another user's project."""
    # Create project as superuser
    resp = await client.post(
        "/api/v1/projects/",
        headers=superuser_headers,
        json={"name": "Admin Project"},
    )
    project_id = resp.json()["id"]

    # Try to access analytics as regular user
    response = await client.get(
        f"/api/v1/analytics/{project_id}/overview",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overview_empty_project(client: AsyncClient, auth_headers: dict):
    """Test overview with no events."""
    resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Empty Project"},
    )
    project_id = resp.json()["id"]

    response = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 0
    assert data["unique_sessions"] == 0
    assert data["unique_users"] == 0
    assert data["top_event"] is None
