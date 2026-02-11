import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers: dict):
    """Test creating a new project."""
    response = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "My Website", "domain": "example.com"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Website"
    assert data["domain"] == "example.com"
    assert data["api_key"].startswith("proj_")
    assert "id" in data


@pytest.mark.asyncio
async def test_create_project_no_domain(client: AsyncClient, auth_headers: dict):
    """Test creating a project without a domain."""
    response = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "My App"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My App"
    assert data["domain"] is None


@pytest.mark.asyncio
async def test_create_project_unauthenticated(client: AsyncClient):
    """Test creating a project without auth fails."""
    response = await client.post(
        "/api/v1/projects/",
        json={"name": "Unauthorized"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers: dict):
    """Test listing user's projects."""
    # Create two projects
    await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Project 1"},
    )
    await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Project 2"},
    )

    response = await client.get("/api/v1/projects/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict):
    """Test getting a specific project."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Test Project"},
    )
    project_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Test Project"


@pytest.mark.asyncio
async def test_get_other_users_project(
    client: AsyncClient, auth_headers: dict, superuser: User, superuser_headers: dict
):
    """Test that a user cannot access another user's project."""
    # Create project as superuser
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=superuser_headers,
        json={"name": "Admin Project"},
    )
    project_id = create_resp.json()["id"]

    # Try to access as regular user
    response = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers: dict):
    """Test updating a project."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Original Name"},
    )
    project_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "Updated Name", "domain": "new.example.com"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["domain"] == "new.example.com"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers: dict):
    """Test deleting a project."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "To Delete"},
    )
    project_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's gone
    response = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rotate_api_key(client: AsyncClient, auth_headers: dict):
    """Test rotating a project's API key."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=auth_headers,
        json={"name": "Key Rotation"},
    )
    data = create_resp.json()
    project_id = data["id"]
    old_key = data["api_key"]

    response = await client.post(
        f"/api/v1/projects/{project_id}/rotate-key",
        headers=auth_headers,
    )
    assert response.status_code == 200
    new_key = response.json()["api_key"]
    assert new_key != old_key
    assert new_key.startswith("proj_")


@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient, auth_headers: dict):
    """Test getting a project that doesn't exist."""
    response = await client.get("/api/v1/projects/99999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_nonexistent_project(client: AsyncClient, auth_headers: dict):
    """Test updating a project that doesn't exist returns 404."""
    response = await client.patch(
        "/api/v1/projects/99999",
        headers=auth_headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_project(client: AsyncClient, auth_headers: dict):
    """Test deleting a project that doesn't exist returns 404."""
    response = await client.delete("/api/v1/projects/99999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_other_users_project(
    client: AsyncClient, auth_headers: dict, superuser: User, superuser_headers: dict
):
    """Test that a user cannot update another user's project."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=superuser_headers,
        json={"name": "Admin Only"},
    )
    project_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_other_users_project(
    client: AsyncClient, auth_headers: dict, superuser: User, superuser_headers: dict
):
    """Test that a user cannot delete another user's project."""
    create_resp = await client.post(
        "/api/v1/projects/",
        headers=superuser_headers,
        json={"name": "Admin Protected"},
    )
    project_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert response.status_code == 403
