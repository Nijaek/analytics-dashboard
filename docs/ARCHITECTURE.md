# Architecture Guide

A privacy-first, self-hosted analytics platform — the Mixpanel/Amplitude alternative you own end-to-end. Track events from any web app via a lightweight JavaScript SDK, process them through an async Redis-backed pipeline, and query aggregated metrics through a real-time dashboard.

**4-service architecture:**

| Service    | Stack                        | Port  |
|------------|------------------------------|-------|
| API        | FastAPI (Python 3.12)        | 8000  |
| Frontend   | Next.js 14 (React 18)       | 3000  |
| Database   | PostgreSQL 16                | 5432  |
| Cache/Queue| Redis 7                      | 6379  |

**Design principles:** async event pipeline (decouple ingestion from persistence), hybrid rollup queries (pre-aggregated for completed hours, raw for current hour), security-by-default (HTTP-only cookies, server-side IP hashing, fail-closed token revocation).

---

## Project Structure

```
analytics-dashboard/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/                # Route layer
│   │   │   ├── deps.py         # FastAPI dependency injection (auth, API key)
│   │   │   └── v1/             # Versioned endpoints
│   │   │       ├── router.py   # Route registration
│   │   │       ├── auth.py     # Login, register, token refresh, logout, WS tickets
│   │   │       ├── events.py   # Event ingestion (API key auth)
│   │   │       ├── analytics.py# Overview, timeseries, top events, sessions, users
│   │   │       ├── projects.py # CRUD + API key rotation
│   │   │       ├── users.py    # User management (superuser endpoints)
│   │   │       ├── ws.py       # WebSocket live event stream
│   │   │       └── health.py   # Health + readiness checks
│   │   ├── core/               # Cross-cutting concerns
│   │   │   ├── config.py       # Pydantic Settings (env vars)
│   │   │   ├── security.py     # JWT, bcrypt, token revocation, account lockout, WS tickets
│   │   │   ├── stream.py       # Redis Stream + pub/sub helpers
│   │   │   ├── redis.py        # Redis client management
│   │   │   ├── limiter.py      # Rate limiting (slowapi)
│   │   │   ├── exceptions.py   # Custom HTTP exceptions
│   │   │   └── validators.py   # Shared validation logic
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── user.py         # User (auth, roles)
│   │   │   ├── project.py      # Project (API keys, hashed storage)
│   │   │   ├── event.py        # Event (append-only) + EventRollupHourly
│   │   │   └── base.py         # TimestampMixin (created_at, updated_at)
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── services/           # Business logic layer
│   │   │   ├── analytics_service.py
│   │   │   ├── event_service.py
│   │   │   ├── project_service.py
│   │   │   ├── user_service.py
│   │   │   └── base.py
│   │   ├── db/                 # Database setup (async engine, session)
│   │   ├── main.py             # App factory, middleware, lifespan
│   │   └── worker.py           # Background stream consumer + rollup computer
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest test suite (116 tests)
│   └── requirements-dev.txt
├── frontend/                   # Next.js application
│   └── src/
│       ├── app/                # App Router pages
│       │   ├── page.tsx        # Home / landing
│       │   ├── login/page.tsx
│       │   ├── register/page.tsx
│       │   ├── projects/page.tsx           # Project list
│       │   ├── projects/[id]/page.tsx      # Dashboard (analytics view)
│       │   └── projects/[id]/settings/page.tsx
│       ├── components/
│       │   └── dashboard/      # MetricCard, EventFeed
│       └── lib/
│           ├── api.ts          # Typed fetch wrapper (credentials: include)
│           ├── auth.ts         # Client-side auth state (logged_in cookie check)
│           └── ws.ts           # useLiveEvents() hook (WebSocket + reconnect)
├── sdk/                        # JavaScript tracking SDK
│   ├── src/tracker.js          # Source (~160 lines, zero deps)
│   ├── dist/                   # Built SDK (sdk.js, sdk.min.js)
│   └── build.js                # Build script
├── demo/
│   └── index.html              # SDK demo page
├── docker-compose.dev.yml      # Dev environment (hot reload)
├── docker-compose.yml          # Production environment
├── Makefile                    # Dev commands
└── .github/workflows/ci.yml   # CI pipeline (4 parallel jobs)
```

---

## Backend Architecture

### Layered Design

```
Request → Routes (api/v1/) → Services (services/) → Models (models/) → PostgreSQL
              ↓                     ↓
         Deps (deps.py)      Schemas (schemas/)
```

Routes handle HTTP concerns (validation, status codes, rate limiting). Services contain business logic. Models define the database schema. This isn't just organizational — it means routes never touch the database directly, and services are testable without HTTP.

### Entry Point — `main.py`

The FastAPI app uses a lifespan context manager that creates a managed Redis client on startup and disposes of engine + Redis on shutdown. Middleware stack:

1. **Rate limiter** — slowapi, `60/minute` default (configurable via `RATE_LIMIT_PER_MINUTE`)
2. **CORS** — explicit origin allowlist, credentials enabled, specific methods/headers
3. **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, CSP, HSTS (non-debug only)

Routes are mounted at `/api/v1`. The SDK dist directory is served as static files at `/static/sdk`. Swagger UI is at `/api/v1/docs`.

### Configuration — `core/config.py`

All config loads from environment variables via Pydantic Settings. Key fields:

| Setting                        | Default                         | Notes                        |
|--------------------------------|---------------------------------|------------------------------|
| `SECRET_KEY`                   | *(required)*                    | Min 32 chars, validated      |
| `DATABASE_URL`                 | `postgresql+asyncpg://...`      | Must use asyncpg driver      |
| `REDIS_URL`                    | `redis://localhost:6379/0`      |                              |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | `30`                            |                              |
| `REFRESH_TOKEN_EXPIRE_DAYS`    | `7`                             |                              |
| `COOKIE_SECURE`                | `true`                          | Set `false` for local HTTP   |
| `COOKIE_SAMESITE`              | `lax`                           |                              |
| `CORS_ORIGINS`                 | `[]`                            | Must be set explicitly       |
| `RATE_LIMIT_PER_MINUTE`        | `60`                            |                              |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `10`                 |                              |

### Database

Async SQLAlchemy 2.0 with the `asyncpg` driver. Connection pool managed by the engine (5 base + 10 overflow). Session-per-request via `get_db` dependency. Migrations via Alembic (`backend/alembic/`).

### Models

**User** — email (unique, indexed), bcrypt-hashed password, `is_active`, `is_superuser`. Inherits `BaseModel` (id, created_at, updated_at).

**Project** — belongs to a User (`user_id` FK). API keys are stored as SHA-256 hashes (`api_key_hash`) with a `proj_` prefix kept separately for display (`api_key_prefix`). The `events` relationship cascades deletes.

**Event** — append-only, high volume. Core fields: `event_name`, `distinct_id`, `properties` (JSON), `session_id`, `page_url`, `referrer`, `user_agent`, `ip_hash`, `timestamp`. Composite indexes:

| Index                              | Columns                                     |
|------------------------------------|---------------------------------------------|
| `ix_events_project_timestamp`      | `project_id`, `timestamp`                   |
| `ix_events_project_event_timestamp`| `project_id`, `event_name`, `timestamp`     |
| `ix_events_project_session`        | `project_id`, `session_id`                  |

**EventRollupHourly** — pre-aggregated by `(project_id, event_name, hour)` with unique constraint. Stores `count`, `unique_sessions`, `unique_users`.

### Auth & Security — `core/security.py`

**JWT tokens** — HS256, stored in HTTP-only cookies. Access tokens (30min) + refresh tokens (7d). A non-HTTP-only `logged_in` cookie is set so the frontend can detect auth state without reading the JWT.

**Token revocation** — Redis-backed JTI tracking. Every issued token's JTI is stored in Redis with a TTL matching the token's expiry. Revocation checks are **fail-closed**: if Redis is unavailable, the token is treated as revoked. Refresh rotates both access and refresh tokens and revokes all prior access tokens for the user.

**Account lockout** — 5 failed login attempts → 15-minute lockout via Redis TTL counter. Lockout check is **fail-open** (don't lock users out if Redis is down).

**API keys** — generated with `secrets.token_urlsafe(32)`, prefixed with `proj_`. Only the SHA-256 hash is stored; the plaintext key is shown once at creation and on rotation.

**IP privacy** — `HMAC-SHA256(SECRET_KEY + UTC date, ip)`. The daily-rotating salt prevents long-term tracking while allowing same-day deduplication.

**WebSocket auth** — short-lived single-use tickets (30s TTL) issued via `POST /auth/ws-ticket`, consumed on WebSocket connect. Avoids putting JWTs in query strings.

### Dependency Injection — `api/deps.py`

| Dependency               | Auth mechanism       | Used by                        |
|--------------------------|----------------------|--------------------------------|
| `get_current_user`       | Cookie or Bearer JWT | All authenticated endpoints    |
| `get_current_superuser`  | JWT + `is_superuser` | User management endpoints      |
| `get_project_by_api_key` | `X-API-Key` header   | Event ingestion                |

`get_current_user` checks cookies first, falls back to `Authorization: Bearer` header — this lets both the SPA (cookie-based) and API clients (bearer token) authenticate against the same endpoints.

---

## Event Pipeline

```
  Browser                API Server               Redis                  Worker              Postgres
    │                        │                       │                      │                    │
    │  POST /events/ingest   │                       │                      │                    │
    │───────────────────────>│                       │                      │                    │
    │   (X-API-Key header)   │                       │                      │                    │
    │                        │  XADD events:ingest   │                      │                    │
    │                        │──────────────────────>│                      │                    │
    │                        │                       │  XREADGROUP (batch)  │                    │
    │                        │                       │<─────────────────────│                    │
    │                        │                       │                      │  bulk INSERT       │
    │                        │                       │                      │───────────────────>│
    │                        │                       │  PUBLISH events:live:N                    │
    │                        │                       │<─────────────────────│                    │
    │                        │                       │                      │                    │
    │                        │            WebSocket   │                      │                    │
    │                        │<──────────────────────│  (pub/sub forward)   │                    │
    │                        │    live event push     │                      │                    │
    │<───────────────────────│                       │                      │                    │
```

**Why Redis Stream?** Decouples ingestion latency from database write latency. The API returns `202 Accepted` immediately after `XADD` succeeds. If Redis is unavailable, the ingest endpoint falls back to direct Postgres writes — no data loss, just higher latency.

**Worker** (`app/worker.py`):
- Consumer group: `event_workers`, stream: `events:ingest`
- Reads up to **200 messages** per batch, **2s** block timeout
- Persists batch to Postgres, then publishes each event to `events:live:{project_id}` pub/sub channel for WebSocket delivery
- Computes hourly rollups every **60 seconds** — aggregates `(project_id, event_name)` counts for the current hour into `EventRollupHourly` via upsert
- Graceful shutdown on SIGINT/SIGTERM

**Rollup query strategy:** Analytics endpoints read from `EventRollupHourly` for completed hours and fall back to raw `Event` table for the current (incomplete) hour. This gives fast reads for historical data while keeping real-time accuracy.

---

## Frontend Architecture

Next.js 14 with App Router. All pages use `"use client"` — this is an SPA with cookie-based auth, not a server-rendered app. The backend handles all data fetching.

### Routes

| Path                          | Page                  |
|-------------------------------|-----------------------|
| `/`                           | Home / landing        |
| `/login`                      | Login form            |
| `/register`                   | Registration form     |
| `/projects`                   | Project list          |
| `/projects/[id]`              | Analytics dashboard   |
| `/projects/[id]/settings`     | Project settings      |

### State Management

- **Server state:** TanStack Query with `staleTime: 30s`, `retry: 1`. Configured in `providers.tsx`.
- **Auth state:** the backend sets a non-HTTP-only `logged_in` cookie. `lib/auth.ts` checks for this cookie to decide whether to show authenticated UI. Actual auth is cookie-based (HTTP-only `access_token`).

### API Client — `lib/api.ts`

A typed `fetchApi<T>()` wrapper that sets `credentials: "include"` on every request (sends cookies cross-origin). All endpoint methods are exported from the `api` object. Errors throw `ApiError` with HTTP status code.

### WebSocket — `lib/ws.ts`

`useLiveEvents(projectId)` hook:
- Fetches a single-use ticket via `POST /auth/ws-ticket`
- Connects to `ws://host/api/v1/ws/events/{projectId}?ticket={ticket}`
- Exponential backoff reconnection: base **1s**, max **30s**, up to **10 retries**
- Maintains a rolling buffer of the last 100 events

### Components

- `MetricCard` — displays a single metric (total events, unique sessions, etc.)
- `EventFeed` — live scrolling list powered by `useLiveEvents()`

### Styling

Tailwind CSS.

---

## JavaScript SDK

Vanilla JS, zero dependencies, ~160 lines (source), ~3KB minified. Located at `sdk/src/tracker.js`, built to `sdk/dist/`.

### Integration

```html
<script src="https://your-api/static/sdk/sdk.min.js"
        data-project="proj_YOUR_API_KEY"
        data-api-url="https://your-api">
</script>
```

Auto-initializes from `<script>` tag attributes. Sends an automatic `page_view` on load.

### Batching

Events are queued and flushed when either condition is met:
- Queue reaches **10 events** (`BATCH_SIZE`)
- **2 seconds** elapse since the last enqueue (`FLUSH_INTERVAL`)
- Page `beforeunload` fires (immediate flush)

Failed sends retry up to **3 times** with exponential backoff (`2^attempt * 1000ms`).

### SPA Support

Intercepts `history.pushState` and `history.replaceState`, listens for `popstate`. Fires a `page_view` event on each detected route change.

### Public API

```js
tracker.event("button_click", { button_id: "signup" });  // Track custom event
tracker.identify("user-123", { plan: "pro" });            // Identify user
tracker.reset();                                          // Clear identity + session
tracker.flush();                                          // Force-send queued events
```

### Privacy

No cookies — session ID stored in `sessionStorage` only. IP addresses are never stored; the server hashes them with a daily-rotating HMAC key before persistence.

---

## API Reference

All endpoints are prefixed with `/api/v1`. Full interactive docs at `/api/v1/docs` (Swagger UI).

### Auth

| Method | Path                     | Auth     | Description                           |
|--------|--------------------------|----------|---------------------------------------|
| POST   | `/auth/register`         | None     | Register new user (5/min rate limit)  |
| POST   | `/auth/login`            | None     | Login, returns JWT cookies (10/min)   |
| POST   | `/auth/login/form`       | None     | OAuth2 form login (for Swagger UI)    |
| POST   | `/auth/refresh`          | Cookie   | Rotate access + refresh tokens        |
| POST   | `/auth/logout`           | JWT      | Revoke tokens, clear cookies          |
| POST   | `/auth/ws-ticket`        | JWT      | Get single-use WebSocket ticket       |
| GET    | `/auth/me`               | JWT      | Get current user info                 |

### Projects

| Method | Path                              | Auth | Description                          |
|--------|-----------------------------------|------|--------------------------------------|
| POST   | `/projects/`                      | JWT  | Create project (returns full API key)|
| GET    | `/projects/`                      | JWT  | List user's projects                 |
| GET    | `/projects/{id}`                  | JWT  | Get project details                  |
| PATCH  | `/projects/{id}`                  | JWT  | Update project name/domain           |
| DELETE | `/projects/{id}`                  | JWT  | Delete project (cascades events)     |
| POST   | `/projects/{id}/rotate-key`       | JWT  | Rotate API key                       |

### Events

| Method | Path               | Auth      | Description                       |
|--------|--------------------|-----------|-----------------------------------|
| POST   | `/events/ingest`   | API Key   | Ingest event batch (X-API-Key)    |

### Analytics

| Method | Path                                | Auth | Description                    |
|--------|-------------------------------------|------|--------------------------------|
| GET    | `/analytics/{id}/overview`          | JWT  | Overview metrics (period param)|
| GET    | `/analytics/{id}/timeseries`        | JWT  | Events over time               |
| GET    | `/analytics/{id}/top-events`        | JWT  | Top events by count            |
| GET    | `/analytics/{id}/sessions`          | JWT  | Session analytics (paginated)  |
| GET    | `/analytics/{id}/users`             | JWT  | Identified user analytics      |

### Users (Superuser)

| Method | Path                       | Auth       | Description                    |
|--------|----------------------------|------------|--------------------------------|
| GET    | `/users/`                  | Superuser  | List all users (paginated)     |
| GET    | `/users/{id}`              | JWT        | Get user (own profile or super)|
| PATCH  | `/users/{id}`              | JWT        | Update user profile            |
| POST   | `/users/me/password`       | JWT        | Change own password            |
| POST   | `/users/{id}/password`     | Superuser  | Reset user's password          |
| DELETE | `/users/{id}`              | Superuser  | Delete user                    |

### WebSocket

| Type      | Path                            | Auth   | Description                 |
|-----------|---------------------------------|--------|-----------------------------|
| WebSocket | `/ws/events/{project_id}`       | Ticket | Live event stream           |

### Health

| Method | Path              | Auth | Description              |
|--------|-------------------|------|--------------------------|
| GET    | `/health/`        | None | Basic health check       |
| GET    | `/health/ready`   | None | Readiness (checks DB)    |

---

## Testing

### Backend — pytest

- **116 tests**, `>=75%` coverage required by CI
- Async fixtures in `conftest.py` (async session, test client, Redis mock)
- Run: `make test-backend` or `cd backend && pytest -v --cov=app tests/`

### Frontend — Vitest + React Testing Library + MSW

- **39 test cases** across 6 test files (unit + integration)
- MSW handlers in `src/__tests__/mocks/` for API mocking
- Run: `make test-frontend` or `cd frontend && npm test`

### CI — GitHub Actions (`.github/workflows/ci.yml`)

Triggers on push/PR to `main`. 4 parallel jobs:

| Job              | What it does                                          |
|------------------|-------------------------------------------------------|
| `lint-backend`   | Ruff check + format check + mypy                     |
| `test-backend`   | pytest with `--cov-fail-under=75`                     |
| `lint-frontend`  | ESLint                                                |
| `test-frontend`  | Vitest                                                |

---

## Development Workflow

### Getting Started

```bash
cp .env.example .env          # Configure environment
make dev                       # Docker Compose with hot reload (all 4 services)
```

API at `http://localhost:8000`, frontend at `http://localhost:3000`.

### Make Targets

| Command             | Description                                        |
|---------------------|----------------------------------------------------|
| `make dev`          | Start dev environment (docker-compose.dev.yml)     |
| `make prod`         | Start production environment (detached)            |
| `make down`         | Stop all containers                                |
| `make logs`         | Tail container logs                                |
| `make test`         | Run all tests (backend + frontend)                 |
| `make test-backend` | Run backend tests only                             |
| `make test-frontend`| Run frontend tests only                            |
| `make lint`         | Run Ruff (backend) + ESLint (frontend)             |
| `make format`       | Auto-format backend code (Ruff)                    |
| `make migrate`      | Run Alembic migrations (`alembic upgrade head`)    |
| `make migration`    | Create new migration (`make migration m='...'`)    |
| `make shell`        | Shell into API container                           |
| `make seed`         | Generate seed event data                           |
| `make loadtest`     | Run Locust load tests against localhost:8000       |

### Database Migrations

```bash
make migration m='add user preferences'   # Generate migration
make migrate                               # Apply migrations
```

### Seed Data

```bash
docker compose exec api python -m scripts.seed_events --api-key <YOUR_PROJECT_API_KEY>
```

---

## Key File Reference

| File                                 | Purpose                                              |
|--------------------------------------|------------------------------------------------------|
| `backend/app/main.py`               | App factory, middleware stack, lifespan, static mount |
| `backend/app/core/config.py`        | All Settings (env vars, defaults, validation)        |
| `backend/app/core/security.py`      | JWT, bcrypt, token revocation, lockout, WS tickets   |
| `backend/app/core/stream.py`        | Redis Stream XADD/XREADGROUP + pub/sub helpers       |
| `backend/app/worker.py`             | Background worker (stream consumer + rollups)        |
| `backend/app/api/deps.py`           | Auth dependencies (JWT, API key, superuser)          |
| `backend/app/api/v1/router.py`      | Route registration (all prefixes and tags)           |
| `backend/app/models/event.py`       | Event + EventRollupHourly (indexes, constraints)     |
| `backend/app/services/event_service.py` | Event ingestion + IP hashing                     |
| `frontend/src/app/providers.tsx`     | TanStack Query config (staleTime, retry)             |
| `frontend/src/lib/api.ts`           | Typed API client (all endpoint methods)              |
| `frontend/src/lib/ws.ts`            | WebSocket hook (reconnection, ticket auth)           |
| `sdk/src/tracker.js`                | SDK source (batching, SPA support, public API)       |
| `Makefile`                           | All dev commands                                     |
| `.github/workflows/ci.yml`          | CI pipeline definition                               |
