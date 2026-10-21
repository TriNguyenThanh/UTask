import { describe, expect, it } from "vitest";

import { canUseTeacherSpace, defaultLandingPath, readLoginNotice, resolveLoginTarget } from "@/features/auth/utils";
import { buildMockAuthUser } from "@/mocks/data/authUsers";

const base = { id: "u", email: "u@x.vn", display_name: "U User" };

describe("defaultLandingPath", () => {
  it.each([
    [["STUDENT"], "/my-work"],
    [["TEACHER"], "/teacher"],
    [["TEACHER", "STUDENT"], "/my-work"],
    [["SYSTEM_ADMIN"], "/settings/profile"],
    [["SYSTEM_ADMIN", "TEACHER"], "/teacher"],
    [["SYSTEM_ADMIN", "STUDENT"], "/my-work"],
  ] as const)("roles %j -> %s", (roles, expected) => {
    expect(defaultLandingPath(buildMockAuthUser({ ...base, roles: [...roles] }))).toBe(expected);
  });

  it("sends anonymous users to the student home", () => {
    expect(defaultLandingPath(null)).toBe("/my-work");
  });
});

describe("canUseTeacherSpace / resolveLoginTarget", () => {
  it("requires the TEACHER role", () => {
    expect(canUseTeacherSpace(buildMockAuthUser({ ...base, roles: ["STUDENT"] }))).toBe(false);
    expect(canUseTeacherSpace(buildMockAuthUser({ ...base, roles: ["TEACHER"] }))).toBe(true);
  });

  it("prefers a safe returnTo and ignores an unsafe one", () => {
    const user = buildMockAuthUser({ ...base, roles: ["TEACHER"] });
    expect(resolveLoginTarget({ returnTo: "/courses" }, user)).toBe("/courses");
    expect(resolveLoginTarget({ returnTo: "https://evil.test" }, user)).toBe("/teacher");
  });
});

describe("readLoginNotice", () => {
  it("returns the notice from router state", () => {
    expect(readLoginNotice({ notice: "Xong." })).toBe("Xong.");
  });

  it.each([null, undefined, {}, { notice: "" }, { notice: 5 }, "text"])("ignores %o", (state) => {
    expect(readLoginNotice(state)).toBeNull();
  });
});
