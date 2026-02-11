# Analytics Dashboard

A self-hosted, real-time event analytics platform. Track page views, user interactions, and custom events across your web applications with a lightweight JavaScript SDK, a FastAPI backend, and a Next.js dashboard.

Think of it as a lightweight, self-hosted alternative to PostHog or Mixpanel.

## Features

- **Event Ingestion** — Collect events via a 3KB JavaScript SDK with automatic page view tracking, SPA support, batching, and retry logic
- **Real-time Streaming** — Live event feed via WebSocket with Redis pub/sub fan-out
- **Analytics API** — Overview metrics, timeseries, top events, session analytics, and user analytics with configurable date ranges
- **Dashboard** — Next.js frontend with metric cards, charts, and a live event feed
- **Multi-project** — Create multiple projects, each with its own API key and isolated data
- **Auth** — JWT authentication with token refresh and revocation via Redis
- **Privacy-first** — IP addresses are SHA-256 hashed with a daily rotating salt. No cookies.

## Architecture

```
[User's Website]                    [Next.js Dashboard]
      |                                    |
      | JS SDK (3KB)                       | TanStack Query + WebSocket
      | POST /events/ingest                |
      v                                    v
+--------------------------------------------------+
|                  FastAPI Backend                   |
|                                                    |
|  /events/ingest --> Redis Stream --> BG Worker --> PostgreSQL
|  /analytics/*   <-- Rollup Tables <---------------+
|  /ws/events/*   <-- Redis Pub/Sub                 |
|  /projects/*    --> PostgreSQL                    |
|  /auth/*        --> JWT + Redis                   |
+--------------------------------------------------+
```

Event ingestion is decoupled from database writes via a Redis stream. The ingest endpoint pushes to Redis (fast) and a background worker drains the stream into Postgres in batches, then computes hourly rollups for fast analytics queries.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, SQLAlchemy (async), PostgreSQL, Redis, Alembic |
| Frontend | Next.js 14 (App Router), TypeScript, TanStack Query, Tailwind CSS |
| SDK | Vanilla JavaScript, no dependencies |
| Infrastructure | Docker Compose, GitHub Actions CI |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.12+ (for local backend development)

### Using Docker (recommended)

```bash
# Clone the repo
git clone https://github.com/Nijaek/analytics-dashboard.git
cd analytics-dashboard

# Copy environment file
cp .env.example .env

# Start all services (API, frontend, Postgres, Redis)
make dev
```

This starts:
- **API** at http://localhost:8000 (with Swagger docs at http://localhost:8000/api/v1/docs)
- **Frontend** at http://localhost:3000
- **PostgreSQL** on port 5432
- **Redis** on port 6379

Then run the database migration:

```bash
make migrate
```

### Local Development (without Docker)

**Backend:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Set environment variables (or use .env file)
export DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/analytics
export SECRET_KEY=your-super-secret-key-at-least-32-chars
export REDIS_URL=redis://localhost:6379/0

# Run migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install

# Set the API URL
export NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
```

**Background Worker** (for Redis stream processing and rollup computation):

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

## Usage

### 1. Create an Account and Project

1. Open http://localhost:3000 and register a new account
2. Create a project from the Projects page
3. Copy your project API key from the Settings page

### 2. Add the Tracking SDK

Add this snippet to the `<head>` of your website:

```html
<script>
(function(){
  var s=document.createElement("script");
  s.src="http://localhost:8000/static/sdk/tracker.min.js";
  s.setAttribute("data-project","YOUR_API_KEY");
  s.setAttribute("data-api-url","http://localhost:8000");
  document.head.appendChild(s);
})();
</script>
```

The SDK automatically tracks page views (including SPA route changes). You can also track custom events:

```javascript
// Track a custom event
tracker.event("button_click", { button_id: "signup" });

// Identify a user
tracker.identify("user_42", { plan: "pro" });

// Reset on logout
tracker.reset();
```

### 3. View Analytics

Open your project dashboard at http://localhost:3000/projects/{id} to see:
- Total events, unique sessions, unique users
- Events over time (hourly/daily)
- Top events by count
- Live event feed via WebSocket

### Seed Data

Generate realistic fake events for development:

```bash
make seed
```

Or with options:

```bash
cd backend
python -m scripts.seed_events --api-key YOUR_API_KEY --count 5000 --days 7
```

### Demo Page

Open `demo/index.html` in a browser for an interactive page that lets you fire test events and see the SDK in action.

## API Reference

All endpoints are documented via Swagger UI at http://localhost:8000/api/v1/docs.

### Key Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | None | Create account |
| POST | `/api/v1/auth/login` | None | Get JWT tokens |
| POST | `/api/v1/projects/` | JWT | Create project |
| GET | `/api/v1/projects/` | JWT | List projects |
| POST | `/api/v1/events/ingest` | API Key | Ingest event batch |
| GET | `/api/v1/analytics/{id}/overview` | JWT | Summary metrics |
| GET | `/api/v1/analytics/{id}/timeseries` | JWT | Events over time |
| GET | `/api/v1/analytics/{id}/top-events` | JWT | Top events |
| GET | `/api/v1/analytics/{id}/sessions` | JWT | Session analytics |
| GET | `/api/v1/analytics/{id}/users` | JWT | User analytics |
| WS | `/api/v1/ws/events/{id}` | JWT | Live event stream |

### Event Ingestion

```bash
curl -X POST http://localhost:8000/api/v1/events/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{
    "events": [{
      "event": "page_view",
      "properties": {"path": "/pricing"},
      "session_id": "sess_abc123",
      "page_url": "https://example.com/pricing",
      "timestamp": "2026-02-10T12:00:00Z"
    }]
  }'
```

## Project Structure

```
analytics-dashboard/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/v1/          # Route handlers (auth, projects, events, analytics, ws)
│   │   ├── core/            # Config, security, Redis, rate limiting, stream helpers
│   │   ├── db/              # SQLAlchemy engine and session
│   │   ├── models/          # Database models (User, Project, Event, EventRollupHourly)
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Business logic layer
│   │   ├── main.py          # FastAPI app entry point
│   │   └── worker.py        # Background worker (stream drain + rollups)
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Seed data generator
│   └── tests/               # pytest tests + Locust load test
├── frontend/                # Next.js application
│   └── src/
│       ├── app/             # App Router pages (login, register, projects, dashboard, settings)
│       ├── components/      # Reusable components (MetricCard, EventFeed)
│       ├── lib/             # API client, auth helpers, WebSocket hook
│       └── __tests__/       # Vitest + React Testing Library tests
├── sdk/                     # JavaScript tracking SDK
│   ├── src/tracker.js       # SDK source
│   ├── build.js             # Build/minify script
│   └── dist/                # Built SDK files
├── demo/                    # Interactive demo page
├── docker-compose.yml       # Production Docker setup
├── docker-compose.dev.yml   # Development Docker setup (hot reload)
└── Makefile                 # Development commands
```

## Available Commands

```bash
make help           # Show all commands
make dev            # Start dev environment (Docker)
make prod           # Start production environment
make down           # Stop all containers
make test           # Run all tests (backend + frontend)
make test-backend   # Run backend tests only
make test-frontend  # Run frontend tests only
make lint           # Run linters (ruff + eslint)
make format         # Auto-format code
make migrate        # Run database migrations
make migration m='description'  # Create a new migration
make seed           # Generate seed data
make loadtest       # Run Locust load test
```

## Testing

**Backend** (98 tests — unit, integration, and analytics):

```bash
cd backend
source .venv/bin/activate
pytest -v --cov=app tests/
```

**Frontend** (14 tests — components, auth, API client):

```bash
cd frontend
npm test
```

**Load testing** (requires a running server):

```bash
make loadtest
# Opens Locust UI at http://localhost:8089
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `SECRET_KEY` | — | JWT signing key (min 32 chars) |
| `REDIS_URL` | — | Redis connection string |
| `DEBUG` | `false` | Enable debug mode |
| `CORS_ORIGINS` | `[]` | Allowed CORS origins (JSON array) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `RATE_LIMIT_PER_MINUTE` | `60` | API rate limit |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for frontend |

## License

MIT
