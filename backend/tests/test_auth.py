import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Login (tokens in body + HTTP-only cookies)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test successful login returns tokens and sets auth cookies."""
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

    # Tokens are also set as HTTP-only cookies
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    assert "logged_in" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login fails with invalid credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword123!"},
    )
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


# ---------------------------------------------------------------------------
# Form Login (Swagger UI — tokens in body)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_form_success(client: AsyncClient):
    """Test successful login via OAuth2 form endpoint."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "formlogin@example.com", "password": "TestPassword123!"},
    )

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


# ---------------------------------------------------------------------------
# Password Validation
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Token Refresh (cookie-first, body fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_via_cookie(client: AsyncClient):
    """Test token refresh via cookie (no body needed)."""
    # Register and login — sets auth cookies on the client
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "TestPassword123!"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "TestPassword123!"},
    )

    # Refresh — endpoint reads refresh_token from cookie
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    # New cookies should be set
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_refresh_token_via_body(client: AsyncClient):
    """Test token refresh via body (backward compat)."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshbody@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshbody@example.com", "password": "TestPassword123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Clear cookies so endpoint falls back to body
    client.cookies.clear()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


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

    # Clear cookies so endpoint uses body fallback
    client.cookies.clear()

    # Try to refresh with access token (should fail — wrong token type)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout (cookie-first, body fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_via_cookie(client: AsyncClient):
    """Test logout using cookie-based auth and refresh token."""
    # Register and login
    await client.post(
        "/api/v1/auth/register",
        json={"email": "logoutcookie@example.com", "password": "TestPassword123!"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "logoutcookie@example.com", "password": "TestPassword123!"},
    )

    # Logout — auth from access_token cookie, refresh from refresh_token cookie
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out"


@pytest.mark.asyncio
async def test_logout_via_body(client: AsyncClient):
    """Test logout with tokens passed via header + body (backward compat)."""
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

    # Clear cookies, use header + body
    client.cookies.clear()

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_logout_without_auth(client: AsyncClient):
    """Test logout fails without auth cookie or Bearer token."""
    response = await client.post("/api/v1/auth/logout")
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
    await client.post(
        "/api/v1/auth/register",
        json={"email": "accesslogout@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "accesslogout@example.com", "password": "TestPassword123!"},
    )
    access_token = login_response.json()["access_token"]

    # Clear cookies, use header + body
    client.cookies.clear()

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": access_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Protected Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    """Test get current user via Bearer header."""
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "id" in data


@pytest.mark.asyncio
async def test_get_me_via_cookie(client: AsyncClient):
    """Test get current user via access_token cookie."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "cookieme@example.com", "password": "TestPassword123!"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "cookieme@example.com", "password": "TestPassword123!"},
    )

    # /me should work via cookie (no Authorization header needed)
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "cookieme@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    """Test get current user without auth fails."""
    response = await client.get("/api/v1/auth/me")
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
    """Test protected endpoint fails when using refresh token as Bearer."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshaccess@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshaccess@example.com", "password": "TestPassword123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Clear cookies so endpoint relies on header only
    client.cookies.clear()

    # Try to access with refresh token as Bearer (should fail — wrong type)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token Revocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_token_revoked_after_logout(client: AsyncClient):
    """Test that access token is invalidated after logout."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "revoke@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "revoke@example.com", "password": "TestPassword123!"},
    )
    access_token = login_response.json()["access_token"]

    # Verify access works before logout (via cookie)
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200

    # Logout (cookies auto-sent)
    await client.post("/api/v1/auth/logout")

    # Verify old access token no longer works via Bearer header
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_token_revoked_after_refresh(client: AsyncClient):
    """Test that old access token is revoked after token refresh."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refreshrevoke@example.com", "password": "TestPassword123!"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "refreshrevoke@example.com", "password": "TestPassword123!"},
    )
    old_access_token = login_response.json()["access_token"]

    # Verify access works before refresh
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200

    # Refresh tokens (cookies auto-sent)
    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]

    # Verify old access token no longer works
    client.cookies.clear()
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


# ---------------------------------------------------------------------------
# WebSocket Ticket Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_ticket_requires_auth(client: AsyncClient):
    """Test ws-ticket endpoint requires authentication."""
    response = await client.post("/api/v1/auth/ws-ticket")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ws_ticket_success(client: AsyncClient, auth_headers: dict):
    """Test ws-ticket returns a ticket string."""
    response = await client.post("/api/v1/auth/ws-ticket", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "ticket" in data
    assert isinstance(data["ticket"], str)
    assert len(data["ticket"]) > 0


@pytest.mark.asyncio
async def test_ws_ticket_via_cookie(client: AsyncClient):
    """Test ws-ticket works with cookie auth."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wsticket@example.com", "password": "TestPassword123!"},
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": "wsticket@example.com", "password": "TestPassword123!"},
    )

    # Should work via cookie auth
    response = await client.post("/api/v1/auth/ws-ticket")
    assert response.status_code == 200
    assert "ticket" in response.json()
