# Real-time Analytics Dashboard — Design Document

## Context

We have a production-ready FastAPI starter with JWT auth, user management, PostgreSQL (async SQLAlchemy), Redis, rate limiting, Docker, and CI/CD. The goal is to build a **real-time analytics platform** on top of it to expand our project portfolio — targeting full-stack roles and demonstrating expertise in real-time systems, data analytics, and SaaS architecture.

**What we're building:** A self-hosted event analytics platform (mini PostHog/Mixpanel). Users create projects, embed a tracking snippet on their sites, and view real-time + historical analytics dashboards.

---

## Architecture Overview

```
[User's Website]                    [Next.js Dashboard]
      │                                    │
      │ JS SDK (2KB)                       │ TanStack Query + WebSocket
      │ POST /events/ingest                │
      ▼                                    ▼
┌─────────────────────────────────────────────────┐
│                  FastAPI Backend                 │
│                                                  │
│  /events/ingest ──► Redis Stream ──► BG Worker ──► PostgreSQL
│  /analytics/*   ◄── Rollup Tables ◄──────────────┘
│  /ws/events/*   ◄── Redis Pub/Sub               │
│  /projects/*    ──► PostgreSQL                   │
│  /auth/*        ──► (existing auth system)       │
└─────────────────────────────────────────────────┘
```

**Key design decision:** Event ingestion is decoupled from database writes via a Redis stream. The ingest endpoint pushes to Redis (fast) and a background worker drains the stream into Postgres in batches. This handles burst traffic without blocking.

---

## Tech Stack

### Backend (extending existing)
- **FastAPI** — new routes for projects, events, analytics, WebSocket
- **PostgreSQL** — event storage, rollup tables
- **Redis** — event stream, pub/sub for WebSocket fan-out, existing token store
- **ARQ or BackgroundTasks** — stream-to-Postgres worker
- **Alembic** — migrations for new tables

### Frontend (new)
- **Next.js 14+ (App Router)** with TypeScript
- **Tremor** — dashboard UI components (charts, metric cards, tables)
- **TanStack Query** — data fetching + cache
- **Tailwind CSS** — layout and styling
- **Native WebSocket** — live event feed

### Tracking SDK (new)
- **Vanilla JS** — ~2KB minified, no dependencies
- Auto page-view tracking, manual event API, user identification
- Batched sends (every 2s or 10 events)

---

## Data Model

### New Tables

```sql
-- Projects: one per tracked site/app
projects
├── id              UUID PRIMARY KEY
├── user_id         FK → users (NOT NULL)
├── name            VARCHAR(255) NOT NULL
├── api_key         VARCHAR(64) UNIQUE NOT NULL (indexed)
├── domain          VARCHAR(255) (optional, origin validation)
├── created_at      TIMESTAMPTZ
├── updated_at      TIMESTAMPTZ

-- Raw events: append-only, high volume
events
├── id              UUID PRIMARY KEY
├── project_id      FK → projects (NOT NULL, indexed)
├── event_name      VARCHAR(255) NOT NULL (indexed)
├── distinct_id     VARCHAR(255) (nullable, set by tracker.identify())
├── properties      JSONB
├── session_id      VARCHAR(64) (indexed)
├── page_url        TEXT
├── referrer        TEXT
├── user_agent      TEXT
├── ip_hash         VARCHAR(64) (SHA-256, privacy-safe)
├── timestamp       TIMESTAMPTZ NOT NULL (indexed)
├── created_at      TIMESTAMPTZ

-- Pre-aggregated rollups: materialized by background worker
event_rollups_hourly
├── id              UUID PRIMARY KEY
├── project_id      FK → projects
├── event_name      VARCHAR(255)
├── hour            TIMESTAMPTZ (truncated to hour)
├── count           INTEGER
├── unique_sessions INTEGER
├── unique_users    INTEGER
├── UNIQUE(project_id, event_name, hour)
```

**Privacy:** IPs are hashed with SHA-256 + daily rotating salt. No cookies. Session ID generated per browser session via SDK.

---

## API Endpoints

### New Routes

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/projects/` | JWT | Create project, returns API key |
| GET | `/api/v1/projects/` | JWT | List user's projects |
| GET | `/api/v1/projects/{id}` | JWT | Get project details |
| PATCH | `/api/v1/projects/{id}` | JWT | Update project |
| DELETE | `/api/v1/projects/{id}` | JWT | Delete project |
| POST | `/api/v1/projects/{id}/rotate-key` | JWT | Rotate API key |
| POST | `/api/v1/events/ingest` | API Key | Ingest events (batched) |
| GET | `/api/v1/analytics/{project_id}/overview` | JWT | Summary metrics |
| GET | `/api/v1/analytics/{project_id}/timeseries` | JWT | Events over time |
| GET | `/api/v1/analytics/{project_id}/top-events` | JWT | Top event names |
| GET | `/api/v1/analytics/{project_id}/sessions` | JWT | Session analytics |
| GET | `/api/v1/analytics/{project_id}/users` | JWT | Identified user analytics |
| WS | `/api/v1/ws/events/{project_id}` | JWT | Live event stream |

### Ingest Endpoint Detail

```json
POST /api/v1/events/ingest
Header: X-API-Key: proj_abc123
Body: {
  "events": [
    {
      "event": "page_view",
      "properties": { "path": "/pricing" },
      "distinct_id": "user_42",
      "session_id": "sess_xyz",
      "page_url": "https://example.com/pricing",
      "referrer": "https://google.com",
      "timestamp": "2026-02-10T12:00:00Z"
    }
  ]
}
```

---

## Frontend Pages

| Route | Description |
|-------|-------------|
| `/login`, `/register` | Auth (existing FastAPI endpoints) |
| `/projects` | Project list + create button |
| `/projects/[id]` | Main dashboard |
| `/projects/[id]/settings` | API key, snippet code, config |

### Dashboard Layout (`/projects/[id]`)

- **Top bar**: project name, date range picker (24h/7d/30d/custom)
- **Metric cards** (Tremor): total events, unique sessions, unique users, top event
- **Line chart**: events over time (hourly/daily toggle)
- **Bar chart**: top 10 event names by count
- **Live event feed**: scrolling WebSocket-powered list with event name, properties, timestamp

---

## Tracking SDK

```js
// Auto-loaded via script tag
<script src="https://your-domain/static/sdk/tracker.min.js" data-project="proj_abc123"></script>

// Auto-tracks: page_view (on load + SPA route changes)

// Manual tracking
tracker.event("button_click", { button_id: "signup" });

// User identification
tracker.identify("user_42", { plan: "pro", company: "Acme" });

// Reset on logout
tracker.reset();
```

- Batches events: sends every 2s or when 10 events buffered
- Retry on network failure (exponential backoff, 3 attempts)
- ~2KB minified, no dependencies
- Served as static file from FastAPI at `/static/sdk/`

---

## Implementation Phases

### Phase 0 — Repo Setup & Scaffolding

**Repo creation:**
- Create new directory `~/Documents/GitHub/analytics-dashboard`
- Clone/copy the FastAPI starter as the backend foundation
- Initialize fresh git repo
- Create GitHub repo via `gh repo create Nijaek/analytics-dashboard --public`
- Push initial commit

**Project structure:**
```
analytics-dashboard/
├── backend/          # FastAPI app (copied from fastapi-starter, restructured)
├── frontend/         # Next.js app (new)
├── sdk/              # Tracking SDK (new)
├── demo/             # Interactive demo page
├── docs/plans/       # Design documents
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
└── README.md
```

**Scaffolding:**
- Move existing FastAPI code into `backend/`
- Initialize Next.js app in `frontend/` with Tremor, Tailwind, TanStack Query, TypeScript
- Create `sdk/` directory structure
- Update Docker Compose: add Next.js service, configure networking
- Update CI pipeline: lint + test for both backend and frontend
- Write design doc to `docs/plans/2026-02-10-analytics-dashboard-design.md`
- Set up shared environment config

### Phase 1 — Project Management

- Project model + Alembic migration
- Project CRUD endpoints with API key generation (`secrets.token_urlsafe`)
- API key authentication dependency (separate from JWT auth)
- Event model + migration
- Basic ingest endpoint (direct-to-Postgres, no Redis stream yet)
- Tests for all new endpoints

### Phase 2 — Analytics API

- Aggregation endpoints: timeseries, top events, overview, sessions, users
- Date range filtering + hourly/daily grouping
- Rollup table + migration
- Background worker: compute hourly rollups from raw events
- Pagination for raw event queries
- Tests for aggregation accuracy

### Phase 3 — Real-time Pipeline

- Redis stream for event ingestion (replace direct DB writes)
- Background worker: drain stream → batch insert to Postgres
- Redis pub/sub channels per project
- WebSocket endpoint streaming live events to dashboard clients
- Tests for stream processing + WebSocket connections

### Phase 4 — Next.js Dashboard

- Auth pages (login/register) calling FastAPI
- Project list + creation flow
- Dashboard page: Tremor charts, metric cards, date picker, filters
- Live event feed via WebSocket
- Project settings page with API key display + snippet code
- Responsive layout
- Frontend tests (Vitest + React Testing Library)

### Phase 5 — Tracking SDK + Demo Data

- Vanilla JS SDK with page-view auto-tracking
- `event()`, `identify()`, `reset()` methods
- Batching + retry logic
- SPA route change detection
- Minified build, served as static asset from backend

**Seed script (`scripts/seed_events.py`):**
- Python script using httpx to generate realistic fake events
- Simulates 7 days of traffic: page views, button clicks, form submissions, signups
- Randomized timestamps, session IDs, user agents, referrers
- Configurable: event count, date range, project API key
- Run via `make seed` or `python scripts/seed_events.py`

**Demo page (`demo/index.html`):**
- Simple static HTML page with the SDK embedded
- Buttons that fire different event types (click, signup, purchase)
- Shows the SDK integration in action — great for portfolio walkthroughs
- Served locally or via Docker

- Integration test: SDK → ingest → dashboard

---

## Key Files to Create/Modify

### Backend (modify existing project)
- `app/models/project.py` — Project model
- `app/models/event.py` — Event + EventRollup models
- `app/schemas/project.py` — Project schemas
- `app/schemas/event.py` — Event ingest schemas
- `app/schemas/analytics.py` — Analytics response schemas
- `app/services/project_service.py` — Project CRUD + API key management
- `app/services/event_service.py` — Event ingestion + stream processing
- `app/services/analytics_service.py` — Aggregation queries
- `app/api/v1/projects.py` — Project endpoints
- `app/api/v1/events.py` — Ingest endpoint
- `app/api/v1/analytics.py` — Analytics endpoints
- `app/api/v1/ws.py` — WebSocket endpoint
- `app/api/deps.py` — Add API key auth dependency
- `app/api/v1/router.py` — Register new route groups
- `app/core/stream.py` — Redis stream helpers
- `alembic/versions/` — New migrations

### Frontend (new Next.js app)
- `frontend/src/app/` — App Router pages
- `frontend/src/components/dashboard/` — Chart, MetricCard, EventFeed components
- `frontend/src/lib/api.ts` — API client
- `frontend/src/lib/ws.ts` — WebSocket hook
- `frontend/src/lib/auth.ts` — Auth context/provider

### SDK (new)
- `sdk/src/tracker.js` — Core tracking logic
- `sdk/build.js` — Minification script

### Demo & Seed Data (new)
- `scripts/seed_events.py` — Generates realistic fake events for development/demos
- `demo/index.html` — Interactive demo page with SDK embedded

---

## Verification

1. `docker compose up` — all services start (FastAPI, Next.js, Postgres, Redis)
2. Register a user → create a project → copy API key
3. Embed SDK snippet on a test HTML page → open it in browser
4. Open dashboard → see page_view events streaming in real time
5. Call `tracker.event()` and `tracker.identify()` → verify in dashboard
6. Switch date ranges → verify chart data updates
7. Run `pytest` — all backend tests pass
8. Run `npm test` in frontend — all frontend tests pass
9. Run Locust load test against ingest endpoint → verify throughput
10. CI pipeline passes (lint + test for both backend and frontend)
