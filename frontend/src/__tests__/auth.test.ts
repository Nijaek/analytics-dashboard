import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

// We need to control document.cookie for testing
const originalDescriptor = Object.getOwnPropertyDescriptor(document, "cookie");

import { isAuthenticated, clearTokens } from "@/lib/auth";

describe("auth helpers (cookie-based)", () => {
  let cookieStore: Record<string, string> = {};

  beforeEach(() => {
    cookieStore = {};
    Object.defineProperty(document, "cookie", {
      get: () =>
        Object.entries(cookieStore)
          .map(([k, v]) => `${k}=${v}`)
          .join("; "),
      set: (value: string) => {
        const [pair] = value.split(";");
        const [key, val] = pair.split("=");
        if (value.includes("max-age=0")) {
          delete cookieStore[key.trim()];
        } else {
          cookieStore[key.trim()] = val?.trim() ?? "";
        }
      },
      configurable: true,
    });
  });

  afterEach(() => {
    // Restore original cookie descriptor
    if (originalDescriptor) {
      Object.defineProperty(document, "cookie", originalDescriptor);
    }
  });

  it("isAuthenticated returns false when no logged_in cookie", () => {
    expect(isAuthenticated()).toBe(false);
  });

  it("isAuthenticated returns true when logged_in cookie exists", () => {
    cookieStore["logged_in"] = "true";
    expect(isAuthenticated()).toBe(true);
  });

  it("clearTokens removes the logged_in cookie", () => {
    cookieStore["logged_in"] = "true";
    expect(isAuthenticated()).toBe(true);
    clearTokens();
    expect(isAuthenticated()).toBe(false);
  });

  it("isAuthenticated is false after clearTokens", () => {
    cookieStore["logged_in"] = "true";
    clearTokens();
    expect(isAuthenticated()).toBe(false);
  });
});
