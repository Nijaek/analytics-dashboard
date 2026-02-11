import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_get_own_user(client: AsyncClient, auth_headers: dict, test_user: User):
    """Test user can get their own profile."""
    response = await client.get(f"/api/v1/users/{test_user.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email


@pytest.mark.asyncio
async def test_get_other_user_forbidden(client: AsyncClient, auth_headers: dict):
    """Test non-superuser cannot access other users' profiles (IDOR protection)."""
    response = await client.get("/api/v1/users/99999", headers=auth_headers)
    assert response.status_code == 404  # Returns 404 to not reveal user existence


@pytest.mark.asyncio
async def test_update_own_user(client: AsyncClient, auth_headers: dict, test_user: User):
    """Test user can update their own profile."""
    response = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=auth_headers,
        json={"full_name": "Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_list_users_requires_superuser(client: AsyncClient, auth_headers: dict):
    """Test listing users requires superuser privileges."""
    response = await client.get("/api/v1/users/", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_users_as_superuser(client: AsyncClient, superuser_headers: dict):
    """Test superuser can list all users."""
    response = await client.get("/api/v1/users/", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_superuser_can_get_any_user(
    client: AsyncClient, superuser_headers: dict, test_user: User
):
    """Test superuser can access any user's profile."""
    response = await client.get(f"/api/v1/users/{test_user.id}", headers=superuser_headers)
    assert response.status_code == 200
    assert response.json()["email"] == test_user.email


@pytest.mark.asyncio
async def test_delete_user_as_superuser(
    client: AsyncClient, superuser_headers: dict, test_user: User
):
    """Test superuser can delete users."""
    response = await client.delete(f"/api/v1/users/{test_user.id}", headers=superuser_headers)
    assert response.status_code == 204

    # Verify deletion
    response = await client.get(f"/api/v1/users/{test_user.id}", headers=superuser_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_requires_superuser(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """Test regular user cannot delete users."""
    response = await client.delete(f"/api/v1/users/{test_user.id}", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_user_email(client: AsyncClient, auth_headers: dict, test_user: User):
    """Test user can update their email."""
    response = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=auth_headers,
        json={"email": "newemail@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "newemail@example.com"


@pytest.mark.asyncio
async def test_update_user_email_conflict(
    client: AsyncClient, auth_headers: dict, test_user: User, db_session: AsyncSession
):
    """Test updating to existing email fails."""
    # Create another user
    other_user = User(
        email="existing@example.com",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Other User",
    )
    db_session.add(other_user)
    await db_session.commit()

    # Try to update to existing email
    response = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=auth_headers,
        json={"email": "existing@example.com"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_user_password_via_patch_ignored(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """Test that password field in PATCH is ignored (must use /me/password)."""
    # Password field is not in UserUpdate schema, so it should be ignored
    response = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=auth_headers,
        json={"password": "NewPassword456!", "full_name": "Updated"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated"

    # Verify the original password still works (password change was ignored)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPassword123!"},
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient, auth_headers: dict, test_user: User):
    """Test user can change password via dedicated endpoint."""
    response = await client.post(
        "/api/v1/users/me/password",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "new_password": "NewSecurePassword456!",
        },
    )
    assert response.status_code == 204

    # Verify new password works
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "NewSecurePassword456!"},
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    """Test password change fails with wrong current password."""
    response = await client.post(
        "/api/v1/users/me/password",
        headers=auth_headers,
        json={
            "current_password": "WrongPassword123!",
            "new_password": "NewSecurePassword456!",
        },
    )
    assert response.status_code == 400
    assert "current password" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_change_password_weak_new(client: AsyncClient, auth_headers: dict, test_user: User):
    """Test password change fails with weak new password."""
    response = await client.post(
        "/api/v1/users/me/password",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "new_password": "weak",
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_superuser_reset_password(
    client: AsyncClient,
    superuser_headers: dict,
    test_user: User,
):
    """Test superuser can reset user password without current password."""
    response = await client.post(
        f"/api/v1/users/{test_user.id}/password",
        headers=superuser_headers,
        json={"new_password": "ResetPassword789!"},
    )
    assert response.status_code == 204

    # Verify new password works
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ResetPassword789!"},
    )
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_regular_user_cannot_reset_others_password(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Test regular user cannot reset another user's password."""
    # Create another user
    other_user = User(
        email="other_pw@example.com",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Other User",
    )
    db_session.add(other_user)
    await db_session.flush()
    await db_session.refresh(other_user)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/users/{other_user.id}/password",
        headers=auth_headers,
        json={"new_password": "HackedPassword123!"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_other_user_forbidden(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
):
    """Test user cannot update other users' profiles."""
    # Create another user
    other_user = User(
        email="other@example.com",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Other User",
    )
    db_session.add(other_user)
    await db_session.flush()
    await db_session.refresh(other_user)
    await db_session.commit()

    # Try to update other user
    response = await client.patch(
        f"/api/v1/users/{other_user.id}",
        headers=auth_headers,
        json={"full_name": "Hacked Name"},
    )
    assert response.status_code == 404  # Returns 404 to not reveal user existence


@pytest.mark.asyncio
async def test_superuser_update_any_user(
    client: AsyncClient, superuser_headers: dict, test_user: User
):
    """Test superuser can update any user's profile."""
    response = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=superuser_headers,
        json={"full_name": "Admin Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Admin Updated Name"


@pytest.mark.asyncio
async def test_get_nonexistent_user_as_superuser(client: AsyncClient, superuser_headers: dict):
    """Test superuser gets 404 for non-existent user."""
    response = await client.get("/api/v1/users/99999", headers=superuser_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_nonexistent_user_as_superuser(client: AsyncClient, superuser_headers: dict):
    """Test superuser gets 404 when updating non-existent user."""
    response = await client.patch(
        "/api/v1/users/99999",
        headers=superuser_headers,
        json={"full_name": "Ghost"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_user(client: AsyncClient, superuser_headers: dict):
    """Test deleting non-existent user returns 404."""
    response = await client.delete("/api/v1/users/99999", headers=superuser_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_users_pagination(
    client: AsyncClient, superuser_headers: dict, db_session: AsyncSession
):
    """Test list users pagination."""
    # Create multiple users
    for i in range(5):
        user = User(
            email=f"paguser{i}@example.com",
            hashed_password=hash_password("TestPassword123!"),
            full_name=f"Pagination User {i}",
        )
        db_session.add(user)
    await db_session.commit()

    # Test first page
    response = await client.get("/api/v1/users/?page=1&per_page=2", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2
    assert data["total"] >= 5  # At least the 5 we created plus superuser
