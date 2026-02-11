const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends RequestInit {
  token?: string;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(data.detail || "Request failed", response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Auth
export const api = {
  login: (email: string, password: string) =>
    fetchApi<{ access_token: string; refresh_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, fullName?: string) =>
    fetchApi("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),

  getMe: (token: string) =>
    fetchApi<{ id: number; email: string; full_name: string | null }>("/api/v1/auth/me", { token }),

  // Projects
  listProjects: (token: string) =>
    fetchApi<Array<{ id: number; name: string; api_key: string; domain: string | null; created_at: string }>>("/api/v1/projects/", { token }),

  createProject: (token: string, name: string, domain?: string) =>
    fetchApi("/api/v1/projects/", {
      method: "POST",
      token,
      body: JSON.stringify({ name, domain }),
    }),

  getProject: (token: string, id: number) =>
    fetchApi<{ id: number; name: string; api_key: string; domain: string | null }>(`/api/v1/projects/${id}`, { token }),

  updateProject: (token: string, id: number, data: { name?: string; domain?: string }) =>
    fetchApi(`/api/v1/projects/${id}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  deleteProject: (token: string, id: number) =>
    fetchApi(`/api/v1/projects/${id}`, { method: "DELETE", token }),

  rotateKey: (token: string, id: number) =>
    fetchApi<{ id: number; name: string; api_key: string; domain: string | null }>(`/api/v1/projects/${id}/rotate-key`, {
      method: "POST",
      token,
    }),

  // Analytics
  getOverview: (token: string, projectId: number, period: string = "24h") =>
    fetchApi<{
      total_events: number;
      unique_sessions: number;
      unique_users: number;
      top_event: string | null;
    }>(`/api/v1/analytics/${projectId}/overview?period=${period}`, { token }),

  getTimeseries: (token: string, projectId: number, period: string = "24h", granularity: string = "hourly") =>
    fetchApi<{
      data: Array<{ timestamp: string; count: number }>;
      granularity: string;
    }>(`/api/v1/analytics/${projectId}/timeseries?period=${period}&granularity=${granularity}`, { token }),

  getTopEvents: (token: string, projectId: number, period: string = "24h") =>
    fetchApi<{
      data: Array<{ event_name: string; count: number; unique_sessions: number; unique_users: number }>;
    }>(`/api/v1/analytics/${projectId}/top-events?period=${period}`, { token }),
};

export { ApiError };
