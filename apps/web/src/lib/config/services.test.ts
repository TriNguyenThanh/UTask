import { describe, expect, it, vi } from "vitest";

import { isRealService, parseRealServices } from "@/lib/config/services";

describe("parseRealServices", () => {
  it("returns an empty set for undefined, empty and blank input", () => {
    expect(parseRealServices(undefined).size).toBe(0);
    expect(parseRealServices("").size).toBe(0);
    expect(parseRealServices(" , ,").size).toBe(0);
  });

  it("parses a trimmed comma-separated list and deduplicates", () => {
    expect([...parseRealServices(" auth , classroom,auth")].sort()).toEqual(["auth", "classroom"]);
  });

  it("accepts the integration service", () => {
    expect([...parseRealServices("auth,integration")].sort()).toEqual(["auth", "integration"]);
  });

  it("throws on unknown names so typos do not silently fall back to mocks", () => {
    expect(() => parseRealServices("auth,clasroom")).toThrow(
      "VITE_REAL_SERVICES chứa giá trị không hợp lệ: clasroom",
    );
  });
});

describe("isRealService", () => {
  it("reads the env value at call time", () => {
    vi.stubEnv("VITE_REAL_SERVICES", "auth");
    expect(isRealService("auth")).toBe(true);
    expect(isRealService("classroom")).toBe(false);

    vi.stubEnv("VITE_REAL_SERVICES", "");
    expect(isRealService("auth")).toBe(false);
  });
});
