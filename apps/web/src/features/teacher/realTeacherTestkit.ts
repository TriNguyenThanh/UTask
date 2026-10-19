import { screen, within } from "@testing-library/react";
import { http } from "msw";
import { vi } from "vitest";

import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildEnrollment,
  buildGroup,
  buildMember,
  buildTeacher,
  classroomHandlers,
  type ClassroomFixture,
} from "@/test/classroomHandlers";
import { renderAppRoutes, teacherTestSession } from "@/test/render";

/** Shared setup for tests of the teacher area against the (simulated) real Classroom service. */

export function fixture(overrides: Partial<ClassroomFixture> = {}): ClassroomFixture {
  return {
    classes: [buildClass()],
    courses: [buildCourse(), buildCourse({ id: "course-2", code: "IT3090", name: "Cơ sở dữ liệu" })],
    teachers: { "class-1": [buildTeacher({ user_id: "tu1" })] },
    enrollments: {
      "class-1": [buildEnrollment({ user_id: "u1" }), buildEnrollment({ id: "e2", user_id: "u2" })],
    },
    groups: { "class-1": [buildGroup({ id: "g1" })] },
    members: { g1: [buildMember({ group_id: "g1", user_id: "u1", role: "LEADER" })] },
    users: [
      { id: "tu1", email: "d@utask.test", student_id: null, display_name: "TS. Đức", avatar_url: null, bio: null, roles: ["TEACHER"], account_status: "ACTIVE" },
      { id: "11111111-1111-4111-8111-111111111111", email: "mai@utask.test", student_id: null, display_name: "ThS. Mai", avatar_url: null, bio: null, roles: ["TEACHER"], account_status: "ACTIVE" },
    ],
    ...overrides,
  };
}

export function setup(route: string, data: ClassroomFixture = fixture(), ...overrides: Parameters<typeof server.use>) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,classroom");
  server.use(...overrides, ...classroomHandlers(data), ...createAuthHandlers("default", createMemoryRepository("default")));
  return renderAppRoutes(route, teacherTestSession);
}

export async function main() {
  return within(await screen.findByRole("main"));
}

export interface Seen {
  key: string | null;
  body: Record<string, unknown>;
}

/** Records the JSON body and Idempotency-Key of each call, answers with `respond`. */
export function record(method: "post" | "patch", path: string, respond: (seen: Seen) => Response): Seen[] {
  const seen: Seen[] = [];
  server.use(
    http[method](path, async ({ request }) => {
      const entry = { key: request.headers.get("Idempotency-Key"), body: (await request.json()) as Record<string, unknown> };
      seen.push(entry);
      return respond(entry);
    }),
  );
  return seen;
}
