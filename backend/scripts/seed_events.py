"""Generate realistic fake events for development and demos.

Usage:
    python -m scripts.seed_events --api-key <PROJECT_API_KEY> [--url http://localhost:8000]
    python -m scripts.seed_events --api-key proj_abc123 --days 7 --count 5000
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

import httpx

PAGES = [
    "/",
    "/pricing",
    "/features",
    "/about",
    "/blog",
    "/blog/getting-started",
    "/blog/best-practices",
    "/docs",
    "/docs/api",
    "/signup",
    "/login",
    "/dashboard",
]

EVENTS = [
    ("page_view", 60),
    ("button_click", 15),
    ("form_submit", 8),
    ("signup", 5),
    ("login", 5),
    ("purchase", 3),
    ("logout", 4),
]

REFERRERS = [
    "https://google.com",
    "https://twitter.com",
    "https://github.com",
    "https://news.ycombinator.com",
    "",
    "",
    "",
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/121.0",
]


def generate_events(count: int, days: int) -> list[dict]:
    """Generate a list of fake events."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    events = []

    # Create some "users"
    num_users = max(count // 20, 10)
    users = [f"user_{i}" for i in range(num_users)]
    sessions = [f"sess_{i:06d}" for i in range(num_users * 3)]

    # Weighted event selection
    event_names = [e[0] for e in EVENTS]
    event_weights = [e[1] for e in EVENTS]

    for _ in range(count):
        event_name = random.choices(event_names, weights=event_weights, k=1)[0]
        user = random.choice(users) if random.random() > 0.3 else None
        session = random.choice(sessions)
        page = random.choice(PAGES)
        ts = start + timedelta(seconds=random.randint(0, days * 86400))

        evt = {
            "event": event_name,
            "session_id": session,
            "page_url": f"https://example.com{page}",
            "referrer": random.choice(REFERRERS) or None,
            "timestamp": ts.isoformat(),
        }

        if user:
            evt["distinct_id"] = user

        # Add properties based on event type
        if event_name == "button_click":
            evt["properties"] = {"button_id": random.choice(["cta", "nav", "signup", "pricing"])}
        elif event_name == "purchase":
            evt["properties"] = {
                "amount": round(random.choice([9.99, 29.99, 49.99, 99.99]), 2),
                "plan": random.choice(["starter", "pro", "enterprise"]),
            }
        elif event_name == "signup":
            evt["properties"] = {"method": random.choice(["email", "google", "github"])}
        elif event_name == "page_view":
            evt["properties"] = {"path": page}

        events.append(evt)

    return events


def main():
    parser = argparse.ArgumentParser(description="Seed analytics events")
    parser.add_argument("--api-key", required=True, help="Project API key")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--count", type=int, default=1000, help="Number of events")
    parser.add_argument("--days", type=int, default=7, help="Days of history")
    parser.add_argument("--batch-size", type=int, default=100, help="Events per request")
    args = parser.parse_args()

    print(f"Generating {args.count} events over {args.days} days...")
    events = generate_events(args.count, args.days)

    # Sort by timestamp for realistic ordering
    events.sort(key=lambda e: e["timestamp"])

    print(f"Sending to {args.url}...")
    total_sent = 0
    with httpx.Client(timeout=30) as client:
        for i in range(0, len(events), args.batch_size):
            batch = events[i : i + args.batch_size]
            resp = client.post(
                f"{args.url}/api/v1/events/ingest",
                json={"events": batch},
                headers={"X-API-Key": args.api_key},
            )
            if resp.status_code == 200:
                total_sent += resp.json()["accepted"]
                print(f"  Sent {total_sent}/{len(events)} events")
            else:
                print(f"  Error: {resp.status_code} - {resp.text}", file=sys.stderr)
                sys.exit(1)

    print(f"Done! Seeded {total_sent} events.")


if __name__ == "__main__":
    main()
