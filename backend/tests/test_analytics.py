from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventRollupHourly
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

    # All events use timestamps after the current hour boundary so the
    # analytics service reads them from the raw Event table (rollup table
    # is only used for completed past hours).
    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    base = current_hour + timedelta(seconds=10)
    events = [
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_1",
            distinct_id="user_1",
            page_url="https://example.com/",
            timestamp=base,
        ),
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_1",
            distinct_id="user_1",
            page_url="https://example.com/pricing",
            timestamp=base + timedelta(seconds=10),
        ),
        Event(
            project_id=project_id,
            event_name="button_click",
            session_id="sess_1",
            distinct_id="user_1",
            properties={"button": "signup"},
            timestamp=base + timedelta(seconds=20),
        ),
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_2",
            distinct_id="user_2",
            page_url="https://example.com/",
            timestamp=base + timedelta(seconds=30),
        ),
        Event(
            project_id=project_id,
            event_name="signup",
            session_id="sess_2",
            distinct_id="user_2",
            timestamp=base + timedelta(seconds=40),
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
async def test_users_analytics(
    client: AsyncClient, auth_headers: dict, project_with_events: dict
):
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
    resp = await client.post(
        "/api/v1/projects/",
        headers=superuser_headers,
        json={"name": "Admin Project"},
    )
    project_id = resp.json()["id"]

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


# ---------------------------------------------------------------------------
# Rollup + raw hybrid tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def project_with_rollups(
    client: AsyncClient,
    auth_headers: dict,
    test_user: User,
    db_session: AsyncSession,
) -> dict:
    """Project with rollup rows for past hours AND raw events for the current hour."""
    resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Rollup Project"},
    )
    project_data = resp.json()
    project_id = project_data["id"]

    now = datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    # Rollup rows for 3 hours ago and 2 hours ago (completed hours)
    rollups = [
        EventRollupHourly(
            project_id=project_id,
            event_name="page_view",
            hour=current_hour - timedelta(hours=3),
            count=100,
            unique_sessions=20,
            unique_users=15,
        ),
        EventRollupHourly(
            project_id=project_id,
            event_name="button_click",
            hour=current_hour - timedelta(hours=3),
            count=30,
            unique_sessions=10,
            unique_users=8,
        ),
        EventRollupHourly(
            project_id=project_id,
            event_name="page_view",
            hour=current_hour - timedelta(hours=2),
            count=80,
            unique_sessions=18,
            unique_users=12,
        ),
    ]
    for rollup in rollups:
        db_session.add(rollup)

    # Raw events for the current (incomplete) hour
    raw_events = [
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_a",
            distinct_id="user_a",
            page_url="https://example.com/",
            timestamp=current_hour + timedelta(seconds=10),
        ),
        Event(
            project_id=project_id,
            event_name="page_view",
            session_id="sess_b",
            distinct_id="user_b",
            page_url="https://example.com/about",
            timestamp=current_hour + timedelta(seconds=20),
        ),
        Event(
            project_id=project_id,
            event_name="button_click",
            session_id="sess_a",
            distinct_id="user_a",
            properties={"button": "cta"},
            timestamp=current_hour + timedelta(seconds=30),
        ),
    ]
    for event in raw_events:
        db_session.add(event)

    await db_session.flush()
    await db_session.commit()
    return project_data


@pytest.mark.asyncio
async def test_overview_rollup_plus_raw(
    client: AsyncClient, auth_headers: dict, project_with_rollups: dict
):
    """Overview combines rollup totals with current-hour raw events."""
    project_id = project_with_rollups["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Rollup: 100+80+30 = 210, Raw: 3 events => 213
    assert data["total_events"] == 213
    # Rollup sessions: 20+10+18=48, Raw sessions: 2 => 50
    assert data["unique_sessions"] == 50
    # Rollup users: 15+8+12=35, Raw users: 2 => 37
    assert data["unique_users"] == 37
    # page_view: 100+80+2=182, button_click: 30+1=31
    assert data["top_event"] == "page_view"


@pytest.mark.asyncio
async def test_timeseries_rollup_plus_raw(
    client: AsyncClient, auth_headers: dict, project_with_rollups: dict
):
    """Timeseries includes rollup hours and current-hour raw data."""
    project_id = project_with_rollups["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/timeseries?period=24h&granularity=hourly",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "hourly"
    points = data["data"]
    # 3 hourly buckets: hour-3, hour-2, current hour
    assert len(points) == 3
    total = sum(p["count"] for p in points)
    assert total == 213


@pytest.mark.asyncio
async def test_top_events_rollup_plus_raw(
    client: AsyncClient, auth_headers: dict, project_with_rollups: dict
):
    """Top events merges rollup and raw counts correctly."""
    project_id = project_with_rollups["id"]
    response = await client.get(
        f"/api/v1/analytics/{project_id}/top-events?period=24h",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2  # page_view and button_click
    # page_view first: 100+80+2 = 182
    assert data[0]["event_name"] == "page_view"
    assert data[0]["count"] == 182
    # button_click: 30+1 = 31
    assert data[1]["event_name"] == "button_click"
    assert data[1]["count"] == 31
