import { describe, it, expect } from "vitest";
import { api, ApiError } from "@/lib/api";

describe("api client", () => {
  it("exports an api object", () => {
    expect(api).toBeDefined();
    expect(typeof api).toBe("object");
  });

  it("has auth methods", () => {
    expect(typeof api.login).toBe("function");
    expect(typeof api.register).toBe("function");
    expect(typeof api.getMe).toBe("function");
  });

  it("has project methods", () => {
    expect(typeof api.listProjects).toBe("function");
    expect(typeof api.createProject).toBe("function");
    expect(typeof api.getProject).toBe("function");
    expect(typeof api.updateProject).toBe("function");
    expect(typeof api.deleteProject).toBe("function");
    expect(typeof api.rotateKey).toBe("function");
  });

  it("has analytics methods", () => {
    expect(typeof api.getOverview).toBe("function");
    expect(typeof api.getTimeseries).toBe("function");
    expect(typeof api.getTopEvents).toBe("function");
  });

  it("exports ApiError class", () => {
    const err = new ApiError("test error", 404);
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("test error");
    expect(err.status).toBe(404);
  });
});
