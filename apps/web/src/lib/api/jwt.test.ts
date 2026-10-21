import { describe, expect, it } from "vitest";

import { jwtExpiry } from "@/lib/api/jwt";

function token(payload: unknown): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "RS256" })}.${encode(payload)}.sig`;
}

describe("jwtExpiry", () => {
  it("reads exp from a base64url payload", () => {
    expect(jwtExpiry(token({ exp: 1_800_000_000, sub: "ü?>" }))).toBe(1_800_000_000);
  });

  it.each([
    ["no dots", "abc"],
    ["not base64", "a.@@@.c"],
    ["not JSON", `a.${btoa("hello")}.c`],
    ["no exp", token({ sub: "x" })],
    ["exp not a number", token({ exp: "soon" })],
    ["empty", ""],
  ])("returns null for %s", (_label, value) => {
    expect(jwtExpiry(value)).toBeNull();
  });
});
