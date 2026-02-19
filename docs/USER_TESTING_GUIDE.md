# Analytics Dashboard — User Testing Guide

A step-by-step walkthrough for testing every feature of the analytics dashboard, from first launch to teardown. This guide also explains *why* the system is built the way it is, so you understand the architecture as you test.

**Time estimate:** 45–60 minutes
**Prerequisites:** Docker Desktop (running), Git, a web browser, a terminal

---

## Table of Contents

1. [Environment Setup](#1-environment-setup)
2. [Account Registration & Login](#2-account-registration--login)
3. [Project Management](#3-project-management)
4. [Seed Test Data](#4-seed-test-data)
5. [Dashboard Analytics Testing](#5-dashboard-analytics-testing)
6. [Live Event Feed (WebSocket)](#6-live-event-feed-websocket)
7. [JavaScript SDK Integration Testing](#7-javascript-sdk-integration-testing)
8. [API Explorer (Swagger UI)](#8-api-explorer-swagger-ui)
9. [Security Feature Verification](#9-security-feature-verification)
10. [Project Deletion & Cleanup Testing](#10-project-deletion--cleanup-testing)
11. [Teardown](#11-teardown)

---

## 1. Environment Setup

### Clone & Start

```bash
git clone <repo-url>
cd analytics-dashboard
make dev
```

`make dev` starts **4 services** via Docker Compose. You'll see log output from all of them in your terminal. Wait until you see health check messages settle down (about 30–60 seconds).

| Service    | URL                              | Purpose                     |
|------------|----------------------------------|-----------------------------|
| Frontend   | http://localhost:3000            | Next.js web app             |
| API        | http://localhost:8000            | FastAPI backend              |
| PostgreSQL | localhost:5432 (internal)        | Persistent data storage     |
| Redis      | localhost:6379 (internal)        | Event streaming & caching   |

### Verify Services Are Running

1. Open http://localhost:3000 — you should see the landing page or login screen.
2. Open http://localhost:8000/api/v1/docs — you should see the Swagger UI (interactive API docs).

If either fails, check the terminal for error messages. Common issues:
- **Port conflict:** Another process is using port 3000 or 8000. Stop it and re-run `make dev`.
- **Docker not running:** Ensure Docker Desktop is started.

> **Architecture Note:** The system uses 4 separate services following separation of concerns. The API and frontend are independent — the frontend is a static Next.js app that calls the API over HTTP. Redis serves double duty: it powers the async event ingestion pipeline (Redis Streams) and handles real-time broadcasting (pub/sub) for the WebSocket live feed. PostgreSQL stores all persistent data (users, projects, events, rollups).

---

## 2. Account Registration & Login

### Register a New Account

1. Navigate to http://localhost:3000/register
2. Fill in the form:
   - **Full Name:** Your name (optional)
   - **Email:** Any valid email (e.g., `test@example.com`)
   - **Password:** Must meet all of these requirements:
     - 12+ characters
     - At least 1 uppercase letter (A–Z)
     - At least 1 lowercase letter (a–z)
     - At least 1 digit (0–9)
     - At least 1 special character (`!@#$%^&*` etc.)
   - Example password: `Testing123!@#`
3. Click **Create Account**
4. You should be redirected to the login page

### Log In

1. Navigate to http://localhost:3000/login (or you'll already be there after registration)
2. Enter your email and password
3. Click **Sign In**
4. **Verify:** You are redirected to `/projects` — the projects list page

> **Architecture Note:** Authentication uses JWT tokens stored in HTTP-only cookies — not localStorage. This is a deliberate security choice: HTTP-only cookies cannot be accessed by JavaScript, which makes them immune to XSS (cross-site scripting) attacks that could steal tokens. The backend sets three cookies on login: an access token (30-minute TTL), a refresh token (7-day TTL, scoped to the auth path only), and a non-HTTP-only "logged-in" flag that the frontend reads to know whether to show authenticated UI. After 5 failed login attempts, the account is locked for 15 minutes (tracked in Redis).

---

## 3. Project Management

### Create a New Project

1. On the `/projects` page, click **New Project**
2. Enter a project name (e.g., "My Test Website")
3. Click **Create**
4. The project appears in the list showing its name, a truncated API key prefix, and creation date
5. Click on the project to open its dashboard

### Copy Your API Key

1. From the dashboard, click **Settings** (top-right)
2. In the **API Key** section, you'll see the full key displayed (format: `proj_...`)
3. Click **Copy** — save this key, you'll need it for seeding data and the SDK demo

### Test Project Settings

1. **Rename:** Change the project name in the General section, click **Save Changes** — verify "Saved" confirmation appears
2. **Set domain:** Enter a domain (e.g., `example.com`), click **Save Changes**
3. **Copy tracking snippet:** Scroll to **Tracking Snippet**, click the **Copy** button in the top-right corner of the code block
4. **Rotate API key:** Click **Rotate API Key** — a browser confirmation dialog asks if you're sure ("The old key will stop working immediately"). Confirm. The key display should update with a new key.

> **Architecture Note:** API keys are SHA-256 hashed before storage in the database — the plaintext key is never persisted. Only the `proj_` prefix is stored in cleartext for display purposes. This means if the database is compromised, API keys cannot be reversed. When you create or rotate a key, the plaintext is shown exactly once in the API response; after that, only the hash exists. This follows the same pattern GitHub uses for personal access tokens.

---

## 4. Seed Test Data

To populate the dashboard with realistic analytics data, run the seed script. Open a **new terminal** (keep `make dev` running in the first one):

```bash
docker compose exec api python -m scripts.seed_events --api-key <YOUR_API_KEY> --count 2000 --days 7
```

Replace `<YOUR_API_KEY>` with the key you copied in the previous step.

**What this generates:**
- ~2,000 events spread across the last 7 days
- Event types with realistic distribution: page views (60%), button clicks (15%), form submits (8%), signups (5%), logins (5%), purchases (3%), logouts (4%)
- 12 different page URLs (/, /pricing, /features, /about, /blog, /docs, etc.)
- Varied referrers (Google, Twitter, GitHub, Hacker News, direct)
- Multiple simulated user agents (Chrome, Firefox, Safari, Android)

**Verify:** Go back to the dashboard at http://localhost:3000/projects/1 (or your project's URL). Metrics should now be populated.

> **Architecture Note:** Events flow through an async pipeline: the SDK (or seed script) sends events to `POST /api/v1/events/ingest`, which pushes them onto a Redis Stream. A background worker process continuously reads batches of 200 messages from the stream, persists them to PostgreSQL in bulk, and publishes each event to a Redis pub/sub channel for real-time WebSocket delivery. This decoupled design means event ingestion is fast (~1ms response time) because the API doesn't wait for database writes. If Redis is unavailable, the API falls back to direct Postgres writes so no data is lost.

---

## 5. Dashboard Analytics Testing

Navigate to your project dashboard (click the project name from `/projects`).

### Metric Cards

Verify the 4 KPI cards across the top:

| Card             | What It Shows                        |
|------------------|--------------------------------------|
| **Total Events** | Count of all events in the period    |
| **Unique Sessions** | Distinct session IDs               |
| **Unique Users** | Distinct user identifiers            |
| **Top Event**    | Most frequent event name             |

### Period Selector

The top-right has three period buttons: **24h**, **7d**, **30d**.

1. Click **7d** — metrics should reflect the last 7 days of seeded data
2. Click **24h** — numbers should drop (only last 24 hours of the seed data)
3. Click **30d** — numbers should match 7d (seed data only covers 7 days)
4. **Verify:** Each click updates all metric cards and both charts below

### Events Over Time Chart

The left panel shows a horizontal bar chart of events over time:

- In **24h** mode: bars represent individual hours (hourly granularity)
- In **7d** or **30d** mode: bars represent individual days (daily granularity)
- Each bar shows a timestamp label and a count value
- The most recent 12 data points are displayed

### Top Events Table

The right panel shows a ranked table with columns:

| Column    | Meaning                              |
|-----------|--------------------------------------|
| Event     | Event name (e.g., `page_view`)       |
| Count     | Total occurrences                    |
| Sessions  | Unique sessions that triggered it    |
| Users     | Unique users that triggered it       |

**Verify:** `page_view` should be the top event (it's 60% of seed data).

### Auto-Refresh

The dashboard automatically refreshes data every **30 seconds**. To verify:
1. Open browser DevTools → Network tab
2. Wait 30 seconds
3. You should see new API requests to `/overview`, `/top-events`, and `/timeseries`

> **Architecture Note:** The analytics system uses a hybrid query strategy. For completed hours, queries read from pre-aggregated `event_rollups_hourly` tables that the background worker computes every 60 seconds. For the current (in-progress) hour, queries hit the raw `events` table directly. This gives you the best of both worlds: fast queries for historical data (reading rollups is orders of magnitude faster than aggregating millions of raw events) and real-time accuracy for the current hour.

---

## 6. Live Event Feed (WebSocket)

The system includes a real-time event streaming infrastructure via WebSocket. The `EventFeed` component connects over WebSocket and shows a live, updating list of events as they're ingested.

### Testing the WebSocket Infrastructure

You can verify the WebSocket pipeline is functional by combining the SDK demo (Section 7) with the dashboard:

1. Open the dashboard for your project in one browser tab
2. Open `demo/index.html` in another tab (see Section 7 for setup)
3. Fire events from the demo — if the EventFeed component is active on the dashboard, events appear in real-time under "Live Events" with a green **Connected** indicator

### How It Works Under the Hood

The WebSocket endpoint is at `ws://localhost:8000/api/v1/ws/events/{project_id}`. To connect, the frontend first requests a single-use authentication ticket via `POST /api/v1/auth/ws-ticket`, then passes it as a query parameter. The connection auto-reconnects with exponential backoff if dropped.

> **Architecture Note:** WebSocket authentication uses single-use tickets with a 30-second TTL instead of putting the JWT directly in the query string. This is a security best practice — query parameters are logged by proxies, CDNs, and web server access logs. A single-use ticket that expires in 30 seconds limits the blast radius if it appears in a log. The real-time event flow uses Redis pub/sub: when the background worker processes an event, it publishes to a `project:{id}` channel, and all WebSocket connections subscribed to that project receive the event instantly.

---

## 7. JavaScript SDK Integration Testing

The repo includes an interactive demo page for the tracking SDK.

### Setup

1. Open `demo/index.html` directly in your browser (File → Open or drag the file into the browser)
2. In the **Project API Key** field, paste your API key (the `proj_...` key from project settings)
3. In the **API URL** field, confirm it says `http://localhost:8000`
4. Click **Initialize SDK**
5. The event log at the bottom should show: `SDK Initialized with key: proj_abc12345...`

### Test Each Action

Click each button and observe the event log:

| Button               | Event Fired     | Properties                              |
|----------------------|-----------------|-----------------------------------------|
| **Page View: /pricing** | `page_view`   | `{path: "/pricing"}`                    |
| **Button Click**     | `button_click`  | `{button: "signup_cta"}`                |
| **Form Submit**      | `form_submit`   | `{form: "contact"}`                     |
| **Purchase ($29.99)**| `purchase`      | `{amount: 29.99, plan: "pro"}`          |
| **Identify User**    | `$identify`     | Random user ID with `{plan, source}`    |
| **Reset / Logout**   | `reset`         | Clears user identity and session        |

### Cross-Verify with Dashboard

1. Fire several events from the demo page
2. Switch to the dashboard tab
3. Wait up to 30 seconds (or until auto-refresh fires)
4. **Verify:** Total Events count has increased, and the new event types appear in Top Events

> **Architecture Note:** The SDK is intentionally minimal — vanilla JavaScript with zero dependencies, roughly 4.5 KB unminified. It uses an IIFE (Immediately Invoked Function Expression) pattern to avoid global scope pollution. Privacy is a first-class concern: the SDK sets no cookies, uses `sessionStorage` (not `localStorage`) for session IDs, contacts no third-party domains, and relies on the server to hash IP addresses with a daily-rotating salt. Events are batched (up to 10 at a time) and flushed every 2 seconds or on page unload, reducing network requests without sacrificing timeliness.

---

## 8. API Explorer (Swagger UI)

The API ships with interactive documentation powered by Swagger UI.

### Access & Authenticate

1. Navigate to http://localhost:8000/api/v1/docs
2. First, get an access token:
   - Find the `POST /api/v1/auth/login/form` endpoint (under **Auth**)
   - Click **Try it out**
   - Enter your email as `username` and your password as `password` (this is OAuth2 form login)
   - Click **Execute**
   - Copy the `access_token` from the response
3. Click the **Authorize** button (top-right, green lock icon)
4. Paste the access token into the **Value** field
5. Click **Authorize**, then **Close**

### Test Analytics Endpoints

Replace `{project_id}` with your project's ID (usually `1` for the first project).

#### Overview Metrics
- **Endpoint:** `GET /api/v1/analytics/{project_id}/overview`
- **Parameters:** `period=7d`
- **Verify:** Response contains `total_events`, `unique_sessions`, `unique_users`, `top_event` matching the dashboard

#### Timeseries
- **Endpoint:** `GET /api/v1/analytics/{project_id}/timeseries`
- **Parameters:** `period=7d`, `granularity=daily`
- **Verify:** Response contains an array of `{timestamp, count}` data points

#### Top Events
- **Endpoint:** `GET /api/v1/analytics/{project_id}/top-events`
- **Parameters:** `period=7d`, `limit=10`
- **Verify:** Response contains a ranked list with `event_name`, `count`, `unique_sessions`, `unique_users`

#### Sessions
- **Endpoint:** `GET /api/v1/analytics/{project_id}/sessions`
- **Parameters:** `period=7d`, `limit=50`
- **Verify:** Response includes session details and pagination metadata

#### Users
- **Endpoint:** `GET /api/v1/analytics/{project_id}/users`
- **Parameters:** `period=7d`
- **Verify:** Response includes identified users (those tracked via `tracker.identify()`)

> **Architecture Note:** The API is versioned at `/api/v1/` from day one, making it possible to introduce breaking changes in a future `/v2/` without disrupting existing integrations. All list endpoints are paginated by default with `limit` and `offset` parameters. The analytics endpoints accept flexible time ranges — you can use the shorthand `period` parameter (24h/7d/30d) or provide explicit `start` and `end` ISO timestamps for custom ranges.

---

## 9. Security Feature Verification

### Rate Limiting

1. Open a terminal and rapidly hit the register endpoint:
   ```bash
   for i in {1..8}; do
     curl -s -o /dev/null -w "%{http_code}\n" \
       -X POST http://localhost:8000/api/v1/auth/register \
       -H "Content-Type: application/json" \
       -d "{\"email\":\"ratelimit${i}@test.com\",\"password\":\"Testing123!@#abc\"}"
   done
   ```
2. **Verify:** The first 5 requests return `201` or `422`. After the 5th, you should see `429 Too Many Requests`.

### Account Lockout

1. Attempt to log in with a **wrong password** 5 times:
   ```bash
   for i in {1..6}; do
     curl -s -w "\n%{http_code}\n" \
       -X POST http://localhost:8000/api/v1/auth/login \
       -H "Content-Type: application/json" \
       -d '{"email":"test@example.com","password":"WrongPassword1!!"}'
   done
   ```
2. **Verify:** After 5 failures, the response should indicate the account is locked. The lockout lasts 15 minutes (tracked in Redis with a TTL).

### Auth Required (Protected Routes)

1. Open an incognito/private browser window
2. Navigate to http://localhost:3000/projects
3. **Verify:** You are redirected to `/login`

### CORS Protection

1. Open browser DevTools → Console on any non-localhost page
2. Run:
   ```javascript
   fetch('http://localhost:8000/api/v1/auth/me', {credentials: 'include'})
     .then(r => console.log('Status:', r.status))
     .catch(e => console.log('Blocked:', e.message))
   ```
3. **Verify:** The request is blocked by CORS policy (only `http://localhost:3000` is allowed)

> **Architecture Note:** Security follows a defense-in-depth strategy with multiple overlapping layers. Rate limiting uses `slowapi` backed by Redis (limits persist across API restarts). Account lockout is stored in Redis with a `login_failures:{email}` key and 15-minute TTL — if Redis goes down, lockout fails open (users can still log in) rather than locking everyone out. Cookies are configured with `HttpOnly` (no JS access), `SameSite=Lax` (CSRF protection), and `Secure` flags. The API also sets security headers including Content Security Policy, HSTS, and X-Frame-Options.

---

## 10. Project Deletion & Cleanup Testing

### Two-Stage Delete

1. Navigate to your project's **Settings** page
2. Scroll to the **Danger Zone** section (red border)
3. Click **Delete Project** — the button expands to show a warning message:
   > "This will permanently delete the project and all its data. This action cannot be undone."
4. You now see two buttons: **Confirm Delete** and **Cancel**
5. Click **Cancel** first — verify the warning collapses back to the single button
6. Click **Delete Project** again, then click **Confirm Delete**
7. **Verify:** You are redirected to `/projects` and the project is no longer listed

> **Architecture Note:** Project deletion uses PostgreSQL foreign key constraints with `ON DELETE CASCADE`. When a project row is deleted, PostgreSQL automatically removes all related events, hourly rollups, and API keys — no application-level cleanup code needed. This is more reliable than application-managed cascades because it's enforced at the database level and executes atomically within a single transaction.

---

## 11. Teardown

When you're done testing, stop all services:

```bash
make down
```

This stops and removes all 4 Docker containers (API, frontend, Postgres, Redis).

**Optional — clear persistent data:**

By default, database and Redis data persist in Docker volumes between restarts. To start completely fresh next time:

```bash
# List volumes to find the exact names (they include your directory name as a prefix)
docker volume ls | grep -E "postgres_data_dev|redis_data_dev"

# Then remove them
docker volume rm analytics-dashboard_postgres_data_dev analytics-dashboard_redis_data_dev
```

### What You Tested

| Area                  | Features Verified                                             |
|-----------------------|---------------------------------------------------------------|
| Environment           | 4-service Docker Compose stack, health checks                 |
| Authentication        | Registration, login, JWT cookies, session management          |
| Project Management    | Create, rename, domain config, API key rotation, delete       |
| Data Ingestion        | Seed script, async Redis Stream pipeline                      |
| Dashboard Analytics   | Metric cards, period selector, timeseries chart, top events   |
| Real-Time             | WebSocket infrastructure, ticket auth, live event delivery    |
| JavaScript SDK        | Event tracking, user identification, session management       |
| API                   | Swagger UI, all analytics endpoints, pagination               |
| Security              | Rate limiting, account lockout, CORS, auth guards, cookies    |
| Data Lifecycle        | Project deletion with cascade cleanup                         |

---

## Quick Command Reference

| Command                | What It Does                                    |
|------------------------|-------------------------------------------------|
| `make dev`             | Start all services (foreground with logs)        |
| `make down`            | Stop all services                                |
| `make logs`            | View container logs (if running detached)        |
| `make seed`            | Run seed script (requires `--api-key`; see Sec 4) |
| `make test`            | Run backend + frontend test suites               |
| `make shell`           | Open a bash shell inside the API container       |
