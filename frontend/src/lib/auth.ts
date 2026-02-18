"use client";

export function isAuthenticated(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split(";").some((c) => c.trim().startsWith("logged_in="));
}

export function clearTokens(): void {
  // Tokens are HTTP-only cookies cleared by the backend logout endpoint.
  // We only clear the client-visible cookie here.
  if (typeof document !== "undefined") {
    document.cookie = "logged_in=; path=/; max-age=0";
  }
}
