import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { publishSession } from "@/features/auth/sessionEvents";
import type { AuthUser } from "@/features/auth/types";
import { LEADER_ID, STUDENT_ID, TEACHER_ID } from "@/mocks/data/database";
import { installPersonaBridge, lookupPersona } from "@/mocks/personaBridge";
import { resolveMockUserId } from "@/mocks/resolveMockUserId";

function user(email: string, roles: NonNullable<AuthUser["roles"]>): AuthUser {
  return { id: "real-id", email, display_name: "Real", global_role: "USER", capabilities: [], roles };
}

function requestWith(authorization?: string): Request {
  return new Request("http://localhost/api/x", { headers: authorization ? { Authorization: authorization } : {} });
}

let uninstall: () => void;

beforeEach(() => {
  uninstall = installPersonaBridge();
});

afterEach(() => {
  publishSession(null);
  uninstall();
});

describe("installPersonaBridge", () => {
  it("maps a real token to the mock persona with the same email, case-insensitively", () => {
    publishSession({ accessToken: "jwt-a", user: user("Leader@UTask.test", ["STUDENT"]) });

    expect(lookupPersona("jwt-a")).toBe(LEADER_ID);
  });

  it("falls back to the teacher persona for TEACHER roles and the student persona otherwise", () => {
    publishSession({ accessToken: "jwt-t", user: user("new.teacher@school.edu", ["TEACHER"]) });
    publishSession({ accessToken: "jwt-s", user: user("new.student@school.edu", ["STUDENT"]) });
    publishSession({ accessToken: "jwt-x", user: user("admin@school.edu", ["SYSTEM_ADMIN"]) });

    expect(lookupPersona("jwt-t")).toBe(TEACHER_ID);
    expect(lookupPersona("jwt-s")).toBe(STUDENT_ID);
    expect(lookupPersona("jwt-x")).toBe(STUDENT_ID);
  });

  it("clears every mapping when the session is cleared", () => {
    publishSession({ accessToken: "jwt-a", user: user("a@school.edu", ["STUDENT"]) });
    publishSession(null);

    expect(lookupPersona("jwt-a")).toBeNull();
  });

  it("stops listening after uninstall", () => {
    uninstall();
    publishSession({ accessToken: "jwt-late", user: user("a@school.edu", ["STUDENT"]) });

    expect(lookupPersona("jwt-late")).toBeNull();
  });
});

describe("resolveMockUserId", () => {
  it("reads the user id from a mock access token", () => {
    expect(resolveMockUserId(requestWith("Bearer mock-access:user-9:default"))).toBe("user-9");
  });

  it("resolves a registered real token through the persona bridge", () => {
    publishSession({ accessToken: "jwt-t", user: user("t@school.edu", ["TEACHER"]) });

    expect(resolveMockUserId(requestWith("Bearer jwt-t"))).toBe(TEACHER_ID);
  });

  it("returns null for unknown tokens, other schemes and missing headers", () => {
    expect(resolveMockUserId(requestWith("Bearer unknown"))).toBeNull();
    expect(resolveMockUserId(requestWith("Basic abc"))).toBeNull();
    expect(resolveMockUserId(requestWith())).toBeNull();
  });
});
