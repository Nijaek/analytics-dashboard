"""Integration tests: full flow from event ingest to analytics queries."""

import pytest
from httpx import AsyncClient

# Import models so Base.metadata.create_all creates all tables
from app.models.event import Event  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.user import User  # noqa: F401


@pytest.fixture
async def project_with_api_key(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a project and return its data along with auth headers."""
    resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Integration Project", "domain": "integration.example.com"},
    )
    assert resp.status_code == 201
    project = resp.json()
    return {
        "project": project,
        "api_key": project["api_key"],
        "auth_headers": auth_headers,
    }


@pytest.mark.asyncio
async def test_full_ingest_to_analytics_flow(client: AsyncClient, project_with_api_key: dict):
    """End-to-end: ingest events via API key, then query all analytics endpoints."""
    api_key = project_with_api_key["api_key"]
    auth_headers = project_with_api_key["auth_headers"]
    project_id = project_with_api_key["project"]["id"]

    # Ingest a batch of diverse events
    events = [
        {
            "event": "page_view",
            "distinct_id": "user_alpha",
            "session_id": "sess_100",
            "page_url": "https://integration.example.com/",
        },
        {
            "event": "page_view",
            "distinct_id": "user_alpha",
            "session_id": "sess_100",
            "page_url": "https://integration.example.com/pricing",
        },
        {
            "event": "button_click",
            "distinct_id": "user_alpha",
            "session_id": "sess_100",
            "properties": {"button": "get_started"},
        },
        {
            "event": "page_view",
            "distinct_id": "user_beta",
            "session_id": "sess_200",
            "page_url": "https://integration.example.com/",
        },
        {
            "event": "signup",
            "distinct_id": "user_beta",
            "session_id": "sess_200",
            "properties": {"plan": "free"},
        },
        {
            "event": "page_view",
            "distinct_id": "user_gamma",
            "session_id": "sess_300",
            "page_url": "https://integration.example.com/docs",
        },
    ]

    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": api_key},
        json={"events": events},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 6

    # -- Overview --
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    overview = resp.json()
    assert overview["total_events"] == 6
    assert overview["unique_sessions"] == 3
    assert overview["unique_users"] == 3
    assert overview["top_event"] == "page_view"  # 4 page_views

    # -- Top events --
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/top-events?period=24h",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    top_events = resp.json()["data"]
    assert len(top_events) == 3  # page_view, button_click, signup
    assert top_events[0]["event_name"] == "page_view"
    assert top_events[0]["count"] == 4

    # -- Timeseries --
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/timeseries?period=24h&granularity=hourly",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    ts = resp.json()
    assert ts["granularity"] == "hourly"
    assert len(ts["data"]) > 0
    total_from_ts = sum(p["count"] for p in ts["data"])
    assert total_from_ts == 6

    # -- Sessions --
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/sessions?period=24h",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    sessions = resp.json()
    assert sessions["total"] == 3
    assert len(sessions["data"]) == 3

    # -- Users --
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/users?period=24h",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    users = resp.json()
    assert users["total"] == 3
    assert len(users["data"]) == 3


@pytest.mark.asyncio
async def test_multiple_projects_isolation(client: AsyncClient, auth_headers: dict):
    """Events in one project must not leak into another project's analytics."""
    # Create two projects
    resp1 = await client.post("/api/v1/projects/", headers=auth_headers, json={"name": "Project A"})
    assert resp1.status_code == 201
    proj_a = resp1.json()

    resp2 = await client.post("/api/v1/projects/", headers=auth_headers, json={"name": "Project B"})
    assert resp2.status_code == 201
    proj_b = resp2.json()

    # Ingest events into Project A only
    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": proj_a["api_key"]},
        json={
            "events": [
                {"event": "page_view", "session_id": "s1", "distinct_id": "u1"},
                {"event": "page_view", "session_id": "s2", "distinct_id": "u2"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 2

    # Project A should have events
    resp = await client.get(
        f"/api/v1/analytics/{proj_a['id']}/overview?period=24h", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total_events"] == 2

    # Project B should have zero events
    resp = await client.get(
        f"/api/v1/analytics/{proj_b['id']}/overview?period=24h", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total_events"] == 0


@pytest.mark.asyncio
async def test_ingest_then_rotate_key(client: AsyncClient, project_with_api_key: dict):
    """After rotating the API key, old key must fail and new key must work."""
    old_api_key = project_with_api_key["api_key"]
    auth_headers = project_with_api_key["auth_headers"]
    project_id = project_with_api_key["project"]["id"]

    # Ingest with old key
    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": old_api_key},
        json={"events": [{"event": "before_rotate", "session_id": "s1"}]},
    )
    assert resp.status_code == 200

    # Rotate the key
    resp = await client.post(f"/api/v1/projects/{project_id}/rotate-key", headers=auth_headers)
    assert resp.status_code == 200
    new_api_key = resp.json()["api_key"]
    assert new_api_key != old_api_key

    # Old key should fail
    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": old_api_key},
        json={"events": [{"event": "should_fail"}]},
    )
    assert resp.status_code == 401

    # New key should work
    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": new_api_key},
        json={"events": [{"event": "after_rotate", "session_id": "s2"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1

    # Analytics should show both ingested events
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total_events"] == 2


@pytest.mark.asyncio
async def test_large_batch_ingest(client: AsyncClient, project_with_api_key: dict):
    """Test ingesting the maximum batch size (100 events)."""
    api_key = project_with_api_key["api_key"]
    auth_headers = project_with_api_key["auth_headers"]
    project_id = project_with_api_key["project"]["id"]

    events = [
        {
            "event": f"event_type_{i % 5}",
            "distinct_id": f"user_{i % 10}",
            "session_id": f"sess_{i % 20}",
            "page_url": f"https://example.com/page/{i}",
        }
        for i in range(100)
    ]

    resp = await client.post(
        "/api/v1/events/ingest",
        headers={"X-API-Key": api_key},
        json={"events": events},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 100

    # Verify analytics reflect all 100 events
    resp = await client.get(
        f"/api/v1/analytics/{project_id}/overview?period=24h", headers=auth_headers
    )
    assert resp.status_code == 200
    overview = resp.json()
    assert overview["total_events"] == 100
    assert overview["unique_sessions"] == 20
    assert overview["unique_users"] == 10


@pytest.mark.asyncio
async def test_auth_flow_register_login_access(client: AsyncClient):
    """Full auth flow: register, login, access protected resource, verify identity."""
    email = "authflow@example.com"
    password = "AuthFlowTest123!"

    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Auth Flow User"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == email

    # Login
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    # Access protected endpoint
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == email

    # Create a project (proves token works for all protected routes)
    resp = await client.post(
        "/api/v1/projects/", headers=headers, json={"name": "Auth Test Project"}
    )
    assert resp.status_code == 201
