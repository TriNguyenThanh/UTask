import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  createProject,
  getProject,
  listProjectMembers,
  listProjects,
  patchProject,
  setProjectArchived,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import { buildProject, buildProjectMember, workHandlers, type WorkCall, type WorkFixture } from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });
const KEY = "11111111-1111-4111-8111-111111111111";

function use(fixture: WorkFixture) {
  const calls: WorkCall[] = [];
  server.use(...workHandlers({ ...fixture, calls }));
  return calls;
}

const CREATE = {
  classroomGroupId: "group-1",
  identifier: "ZP9T",
  name: "Dự án thử",
  description: "",
  targetGoals: "",
  startDate: null,
  endDate: null,
};

describe("listProjects", () => {
  it("merges every page of the list", async () => {
    const projects = [buildProject({ id: "a" }), buildProject({ id: "b" }), buildProject({ id: "c" })];
    use({ projects, pageSize: 2 });
    const result = await listProjects(client, "all");
    expect(result.projects.map((project) => project.id)).toEqual(["a", "b", "c"]);
    expect(result.partial).toBe(false);
  });

  it("reads partial from meta.scope of the first page", async () => {
    use({ projects: [buildProject({ id: "a" }), buildProject({ id: "b" })], pageSize: 1, partial: true });
    expect((await listProjects(client, "all")).partial).toBe(true);
  });

  it("filters by status", async () => {
    use({ projects: [buildProject({ id: "a" }), buildProject({ id: "b", archived_at: "2026-10-01T00:00:00Z" })] });
    expect((await listProjects(client, "archived")).projects.map((project) => project.id)).toEqual(["b"]);
    expect((await listProjects(client, "active")).projects.map((project) => project.id)).toEqual(["a"]);
  });

  it("rethrows the server error as an ApiError with its code", async () => {
    use({ projects: [], listError: { status: 503, code: "CLASSROOM_UNAVAILABLE", message: "Classroom không phản hồi." } });
    const error = await listProjects(client, "all").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: "CLASSROOM_UNAVAILABLE" });
  });

  it("surfaces VALIDATION_ERROR from an unknown status", async () => {
    use({ projects: [] });
    const error = await listProjects(client, "bogus" as never).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 400, code: "VALIDATION_ERROR" });
  });
});

describe("getProject / listProjectMembers", () => {
  it("returns 404 RESOURCE_NOT_FOUND for a project the user cannot see", async () => {
    use({ projects: [] });
    const error = await getProject(client, "missing").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 404, code: "RESOURCE_NOT_FOUND" });
  });

  it("defaults to ACTIVE members and honours an explicit status", async () => {
    use({
      projects: [buildProject()],
      members: {
        "project-1": [
          buildProjectMember({ id: "m1" }),
          buildProjectMember({ id: "m2", status: "LEFT" }),
        ],
      },
    });
    expect((await listProjectMembers(client, "project-1")).map((member) => member.id)).toEqual(["m1"]);
    expect((await listProjectMembers(client, "project-1", "LEFT")).map((member) => member.id)).toEqual(["m2"]);
  });
});

describe("project commands", () => {
  it("createProject sends the idempotency key and a snake_case body with tech_stack {}", async () => {
    const calls = use({ projects: [] });
    const project = await createProject(client, { ...CREATE, idempotencyKey: KEY });
    expect(project.identifier).toBe("ZP9T");
    expect(calls).toEqual([
      {
        method: "POST",
        path: "/projects/",
        idempotencyKey: KEY,
        body: {
          classroom_group_id: "group-1",
          identifier: "ZP9T",
          name: "Dự án thử",
          description: "",
          target_goals: "",
          start_date: null,
          end_date: null,
          tech_stack: {},
        },
      },
    ]);
  });

  it("createProject surfaces DUPLICATE_IDENTIFIER", async () => {
    use({ projects: [buildProject({ identifier: "ZP9T" })] });
    const error = await createProject(client, { ...CREATE, idempotencyKey: KEY }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 409, code: "DUPLICATE_IDENTIFIER" });
  });

  it("patchProject sends only the changed keys plus expected_version", async () => {
    const calls = use({ projects: [buildProject({ version: 3 })] });
    const project = await patchProject(client, "project-1", { name: "Tên mới", endDate: null, expectedVersion: 3 });
    expect(calls[0].body).toEqual({ expected_version: 3, name: "Tên mới", end_date: null });
    expect(project).toMatchObject({ name: "Tên mới", version: 4 });
  });

  it("patchProject surfaces VERSION_CONFLICT on a stale version", async () => {
    use({ projects: [buildProject({ version: 5 })] });
    const error = await patchProject(client, "project-1", { name: "x", expectedVersion: 3 }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 409, code: "VERSION_CONFLICT" });
  });

  it("setProjectArchived picks the path, omits the idempotency key and returns the server version", async () => {
    const calls = use({ projects: [buildProject({ version: 2 })] });
    const archived = await setProjectArchived(client, "project-1", { archived: true, expectedVersion: 2 });
    expect(archived).toMatchObject({ version: 3 });
    expect(archived.archived_at).not.toBeNull();
    const restored = await setProjectArchived(client, "project-1", { archived: false, expectedVersion: 3 });
    expect(restored.archived_at).toBeNull();
    expect(calls.map((call) => [call.path, call.idempotencyKey])).toEqual([
      ["/projects/project-1/archive/", null],
      ["/projects/project-1/unarchive/", null],
    ]);
  });

  it("setProjectArchived on a project already in that state does not bump the version", async () => {
    use({ projects: [buildProject({ version: 2 })] });
    const result = await setProjectArchived(client, "project-1", { archived: false, expectedVersion: 2 });
    expect(result.version).toBe(2);
  });
});
