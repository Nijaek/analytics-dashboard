"""Locust load test for the analytics dashboard event ingest and analytics APIs.

Usage:
    locust -f backend/tests/locustfile.py --host http://localhost:8000
    # or via Makefile:
    make loadtest
"""

import random
import string
import uuid

from locust import HttpUser, between, task

EVENT_TYPES = [
    "page_view",
    "button_click",
    "signup",
    "purchase",
    "form_submit",
    "scroll",
    "video_play",
    "search",
]

PAGES = [
    "/",
    "/pricing",
    "/docs",
    "/blog",
    "/about",
    "/contact",
    "/dashboard",
    "/settings",
    "/login",
    "/signup",
]


def _random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class AnalyticsUser(HttpUser):
    """Simulates an SDK client sending events and querying analytics."""

    wait_time = between(0.5, 2)

    def on_start(self):
        """Register, login, create a project, and save the API key."""
        suffix = _random_string(12)
        self.email = f"loadtest_{suffix}@example.com"
        self.password = "LoadTest123!"

        # Register
        resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": f"Load Test {suffix}",
            },
        )
        if resp.status_code != 201:
            # If registration fails (e.g., duplicate), try login directly
            pass

        # Login
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "password": self.password},
        )
        if resp.status_code != 200:
            self.environment.runner.quit()
            return

        tokens = resp.json()
        self.auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Create a project
        resp = self.client.post(
            "/api/v1/projects/",
            headers=self.auth_headers,
            json={"name": f"Load Test Project {suffix}"},
        )
        if resp.status_code != 201:
            self.environment.runner.quit()
            return

        project = resp.json()
        self.project_id = project["id"]
        self.api_key = project["api_key"]

    @task(10)
    def ingest_events(self):
        """Send a batch of 1-20 random events."""
        batch_size = random.randint(1, 20)
        events = []
        for _ in range(batch_size):
            event = {
                "event": random.choice(EVENT_TYPES),
                "distinct_id": f"user_{random.randint(1, 50)}",
                "session_id": f"sess_{uuid.uuid4().hex[:12]}",
                "page_url": f"https://example.com{random.choice(PAGES)}",
            }
            if random.random() < 0.3:
                event["properties"] = {
                    "button": _random_string(6),
                    "value": random.randint(1, 1000),
                }
            if random.random() < 0.2:
                event["referrer"] = f"https://google.com/search?q={_random_string(5)}"
            events.append(event)

        self.client.post(
            "/api/v1/events/ingest",
            headers={"X-API-Key": self.api_key},
            json={"events": events},
            name="/api/v1/events/ingest",
        )

    @task(3)
    def query_overview(self):
        """Query the overview analytics endpoint."""
        period = random.choice(["24h", "7d", "30d"])
        self.client.get(
            f"/api/v1/analytics/{self.project_id}/overview?period={period}",
            headers=self.auth_headers,
            name="/api/v1/analytics/[id]/overview",
        )

    @task(2)
    def query_timeseries(self):
        """Query the timeseries analytics endpoint."""
        period = random.choice(["24h", "7d", "30d"])
        granularity = random.choice(["hourly", "daily"])
        self.client.get(
            f"/api/v1/analytics/{self.project_id}/timeseries?period={period}&granularity={granularity}",
            headers=self.auth_headers,
            name="/api/v1/analytics/[id]/timeseries",
        )

    @task(2)
    def query_top_events(self):
        """Query the top events analytics endpoint."""
        self.client.get(
            f"/api/v1/analytics/{self.project_id}/top-events?period=24h",
            headers=self.auth_headers,
            name="/api/v1/analytics/[id]/top-events",
        )

    @task(1)
    def query_sessions(self):
        """Query the sessions analytics endpoint."""
        self.client.get(
            f"/api/v1/analytics/{self.project_id}/sessions?period=24h",
            headers=self.auth_headers,
            name="/api/v1/analytics/[id]/sessions",
        )

    @task(1)
    def query_users(self):
        """Query the users analytics endpoint."""
        self.client.get(
            f"/api/v1/analytics/{self.project_id}/users?period=24h",
            headers=self.auth_headers,
            name="/api/v1/analytics/[id]/users",
        )
