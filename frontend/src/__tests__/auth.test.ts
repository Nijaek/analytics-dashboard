import { describe, it, expect, beforeEach, vi } from "vitest";

// Create a proper localStorage mock before importing auth module
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    store[key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete store[key];
  }),
  clear: vi.fn(() => {
    for (const key of Object.keys(store)) {
      delete store[key];
    }
  }),
  get length() {
    return Object.keys(store).length;
  },
  key: vi.fn((index: number) => Object.keys(store)[index] ?? null),
};

Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
  writable: true,
});

import { getToken, setTokens, isAuthenticated, clearTokens } from "@/lib/auth";

describe("auth helpers", () => {
  beforeEach(() => {
    for (const key of Object.keys(store)) {
      delete store[key];
    }
    vi.clearAllMocks();
  });

  it("getToken returns null when no token set", () => {
    expect(getToken()).toBeNull();
  });

  it("setTokens stores access and refresh tokens", () => {
    setTokens("access123", "refresh456");
    expect(store["analytics_token"]).toBe("access123");
    expect(store["analytics_refresh"]).toBe("refresh456");
  });

  it("getToken returns stored access token", () => {
    setTokens("mytoken", "myrefresh");
    expect(getToken()).toBe("mytoken");
  });

  it("isAuthenticated returns false when no token", () => {
    expect(isAuthenticated()).toBe(false);
  });

  it("isAuthenticated returns true when token exists", () => {
    setTokens("tok", "ref");
    expect(isAuthenticated()).toBe(true);
  });

  it("clearTokens removes both tokens", () => {
    setTokens("tok", "ref");
    clearTokens();
    expect(getToken()).toBeNull();
    expect(store["analytics_refresh"]).toBeUndefined();
    expect(isAuthenticated()).toBe(false);
  });
});
