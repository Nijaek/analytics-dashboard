import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "TestPassword123!",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Test registration fails with weak password."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",  # Too short, no uppercase, no digit
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_register_password_without_special_char(client: AsyncClient):
    """Test registration fails without special character in password."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "nospecial@example.com",
            "password": "TestPassword1234",  # Meets length, upper, lower, digit, but no special char
        },
    )
    assert response.status_code == 422
    # Verify the error message mentions special character
    assert "special character" in response.json()["detail"][0]["msg"].lower()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test registration fails with duplicate email."""
    # First registration
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "TestPassword123!"},
    )

    # Duplicate registration
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "AnotherPassword456!"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test successful login."""
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "TestPassword123!"},
    )

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login fails with invalid credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """Test token refresh."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "TestPassword123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Refresh
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    """Test logout revokes refresh token."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "logout@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "TestPassword123!"},
    )
    tokens = login_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Logout (requires Bearer auth)
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    """Test get current user."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "id" in data


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    """Test get current user without auth fails."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session: AsyncSession):
    """Test that inactive users cannot login via /auth/login."""
    user = User(
        email="inactive@example.com",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Inactive User",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "TestPassword123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_form_inactive_user(client: AsyncClient, db_session: AsyncSession):
    """Test that inactive users cannot login via /auth/login/form."""
    user = User(
        email="inactive_form@example.com",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Inactive User Form",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login/form",
        data={"username": "inactive_form@example.com", "password": "TestPassword123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_form_success(client: AsyncClient):
    """Test successful login via OAuth2 form endpoint."""
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={"email": "formlogin@example.com", "password": "TestPassword123!"},
    )

    # Login via form
    response = await client.post(
        "/api/v1/auth/login/form",
        data={"username": "formlogin@example.com", "password": "TestPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_form_invalid_credentials(client: AsyncClient):
    """Test form login fails with invalid credentials."""
    response = await client.post(
        "/api/v1/auth/login/form",
        data={"username": "nobody@example.com", "password": "WrongPassword123!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_missing_uppercase(client: AsyncClient):
    """Test registration fails without uppercase letter."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "noup@example.com", "password": "testpassword123!"},
    )
    assert response.status_code == 422
    assert "uppercase" in response.json()["detail"][0]["msg"].lower()


@pytest.mark.asyncio
async def test_password_missing_lowercase(client: AsyncClient):
    """Test registration fails without lowercase letter."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "nolow@example.com", "password": "TESTPASSWORD123!"},
    )
    assert response.status_code == 422
    assert "lowercase" in response.json()["detail"][0]["msg"].lower()


@pytest.mark.asyncio
async def test_password_missing_digit(client: AsyncClient):
    """Test registration fails without digit."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "nodigit@example.com", "password": "TestPasswordABC!"},
    )
    assert response.status_code == 422
    assert "digit" in response.json()["detail"][0]["msg"].lower()


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    """Test refresh fails with invalid token."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token(client: AsyncClient):
    """Test refresh fails when using access token instead of refresh token."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "accessrefresh@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "accessrefresh@example.com", "password": "TestPassword123!"},
    )
    access_token = login_response.json()["access_token"]

    # Try to refresh with access token (should fail)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_auth(client: AsyncClient):
    """Test logout fails without Bearer token."""
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "some-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_invalid_token(client: AsyncClient, auth_headers: dict):
    """Test logout fails with invalid refresh token."""
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "invalid-token"},
        headers=auth_headers,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_access_token(client: AsyncClient):
    """Test logout fails when using access token instead of refresh token."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "accesslogout@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "accesslogout@example.com", "password": "TestPassword123!"},
    )
    access_token = login_response.json()["access_token"]

    # Try to logout with access token as refresh_token (should fail)
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": access_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_with_invalid_token(client: AsyncClient):
    """Test protected endpoint fails with malformed token."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_with_refresh_token(client: AsyncClient):
    """Test protected endpoint fails when using refresh token."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshaccess@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshaccess@example.com", "password": "TestPassword123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Try to access with refresh token (should fail)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_revoked_after_logout(client: AsyncClient):
    """Test that access token is invalidated after logout."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "revoke@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "revoke@example.com", "password": "TestPassword123!"},
    )
    tokens = login_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify access works before logout
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    # Logout (with auth)
    await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Verify access token no longer works
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_revoked_after_refresh(client: AsyncClient):
    """Test that old access token is revoked after token refresh."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshrevoke@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshrevoke@example.com", "password": "TestPassword123!"},
    )
    tokens = login_response.json()
    old_access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify access works before refresh
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert response.status_code == 200

    # Refresh tokens
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    new_tokens = refresh_response.json()
    new_access_token = new_tokens["access_token"]

    # Verify old access token no longer works
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert response.status_code == 401

    # Verify new access token works
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert response.status_code == 200
