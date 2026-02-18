import { http, HttpResponse } from "msw";

const API_URL = "http://localhost:8000";

export const handlers = [
  // Auth endpoints
  http.post(`${API_URL}/api/v1/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.email === "test@example.com" && body.password === "password123") {
      // Backend sets HTTP-only cookies on the response; we just return a success message.
      return HttpResponse.json({ message: "Login successful" });
    }
    return HttpResponse.json(
      { detail: "Invalid email or password" },
      { status: 401 },
    );
  }),

  http.post(`${API_URL}/api/v1/auth/logout`, () => {
    return HttpResponse.json({ message: "Logged out" });
  }),

  http.post(`${API_URL}/api/v1/auth/register`, () => {
    return HttpResponse.json(
      { id: 1, email: "new@example.com", full_name: "New User" },
      { status: 201 },
    );
  }),

  // Auth is now cookie-based (HTTP-only cookies are sent automatically via
  // credentials: "include"). MSW cannot inspect HTTP-only cookies, so these
  // handlers return data unconditionally — auth validation happens server-side.
  http.get(`${API_URL}/api/v1/auth/me`, () => {
    return HttpResponse.json({
      id: 1,
      email: "test@example.com",
      full_name: "Test User",
    });
  }),

  // Projects
  http.get(`${API_URL}/api/v1/projects/`, () => {
    return HttpResponse.json([
      {
        id: 1,
        name: "My Website",
        api_key: "proj_abc1234567890123",
        domain: "example.com",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: 2,
        name: "Mobile App",
        api_key: "proj_def4567890123456",
        domain: null,
        created_at: "2026-01-15T00:00:00Z",
      },
    ]);
  }),

  http.post(`${API_URL}/api/v1/projects/`, async ({ request }) => {
    const body = (await request.json()) as { name: string; domain?: string };
    return HttpResponse.json(
      {
        id: 3,
        name: body.name,
        api_key: "proj_new7890123456789",
        domain: body.domain || null,
        user_id: 1,
        created_at: "2026-02-01T00:00:00Z",
        updated_at: "2026-02-01T00:00:00Z",
      },
      { status: 201 },
    );
  }),

  // Analytics
  http.get(`${API_URL}/api/v1/analytics/:projectId/overview`, () => {
    return HttpResponse.json({
      total_events: 1234,
      unique_sessions: 567,
      unique_users: 234,
      top_event: "page_view",
      period_start: "2026-02-17T00:00:00Z",
      period_end: "2026-02-18T00:00:00Z",
    });
  }),

  http.get(`${API_URL}/api/v1/analytics/:projectId/timeseries`, () => {
    return HttpResponse.json({
      data: [
        { timestamp: "2026-02-17T10:00:00Z", count: 45 },
        { timestamp: "2026-02-17T11:00:00Z", count: 62 },
      ],
      granularity: "hourly",
    });
  }),

  http.get(`${API_URL}/api/v1/analytics/:projectId/top-events`, () => {
    return HttpResponse.json({
      data: [
        {
          event_name: "page_view",
          count: 800,
          unique_sessions: 400,
          unique_users: 200,
        },
        {
          event_name: "button_click",
          count: 300,
          unique_sessions: 150,
          unique_users: 100,
        },
      ],
    });
  }),

  // Single project
  http.get(`${API_URL}/api/v1/projects/:id`, () => {
    return HttpResponse.json({
      id: 1,
      name: "My Website",
      api_key: "proj_abc1234567890123",
      domain: "example.com",
    });
  }),
];
