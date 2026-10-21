import { http } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { loadGroupProjects, loadProjectCards, loadProjectShell } from "@/lib/api/work/loaders";
import { server } from "@/mocks/server";
import {
  buildClass,
  buildCourse,
  buildGroup,
  classroomHandlers,
  envelopeError,
} from "@/test/classroomHandlers";
import { buildProject, buildProjectMember, workHandlers, type WorkFixture } from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function use(work: WorkFixture, classroom = true) {
  server.use(
    ...workHandlers(work),
    ...(classroom
      ? classroomHandlers({
          classes: [buildClass({ id: "class-1", code: "SE100.A", name: "Lớp A", course: "course-1" })],
          courses: [buildCourse({ id: "course-1", code: "SE100" })],
          groups: { "class-1": [buildGroup({ id: "group-1", name: "Nhóm 1" })] },
        })
      : []),
  );
}

describe("loadProjectCards", () => {
  it("returns an empty list without touching Classroom when the user has no project", async () => {
    // Không đăng ký handler Classroom: gọi tới sẽ làm lời gọi phụ lỗi, nhưng cũng không được xảy ra.
    use({ projects: [] }, false);
    expect(await loadProjectCards(client, "u1")).toEqual({ cards: [], partial: false });
  });

  it("joins class, course, group names and my role", async () => {
    use({
      projects: [buildProject()],
      members: { "project-1": [buildProjectMember({ user_id: "u1", role: "LEADER" })] },
    });
    const { cards } = await loadProjectCards(client, "u1");
    expect(cards[0]).toMatchObject({ classCode: "SE100.A", courseCode: "SE100", groupName: "Nhóm 1", myRole: "LEADER" });
  });

  it("keeps the card with blank fields when a side call fails", async () => {
    use({ projects: [buildProject()] }, false);
    server.use(http.get("/api/classroom/*", () => envelopeError(500, "INTERNAL_ERROR", "Lỗi")));
    const { cards } = await loadProjectCards(client, "u1");
    expect(cards).toHaveLength(1);
    expect(cards[0]).toMatchObject({ classCode: "", courseCode: "", groupName: "", myRole: null });
  });

  it("passes partial through", async () => {
    use({ projects: [buildProject()], partial: true });
    expect((await loadProjectCards(client, "u1")).partial).toBe(true);
  });
});

describe("loadProjectShell", () => {
  it("derives canEdit from a LEADER role on a live project", async () => {
    use({
      projects: [buildProject()],
      members: { "project-1": [buildProjectMember({ user_id: "u1", role: "LEADER" })] },
    });
    const shell = await loadProjectShell(client, "u1", "project-1");
    expect(shell).toMatchObject({ myRole: "LEADER", canEdit: true, groupName: "Nhóm 1", classCode: "SE100.A" });
  });

  it("cannot edit an archived project or as a plain member or non-member", async () => {
    use({
      projects: [buildProject(), buildProject({ id: "project-2", archived_at: "2026-10-01T00:00:00Z" })],
      members: {
        "project-1": [buildProjectMember({ user_id: "u1", role: "MEMBER" })],
        "project-2": [buildProjectMember({ user_id: "u1", role: "LEADER" })],
      },
    });
    expect((await loadProjectShell(client, "u1", "project-1")).canEdit).toBe(false);
    const archived = await loadProjectShell(client, "u1", "project-2");
    expect(archived).toMatchObject({ myRole: "LEADER", canEdit: false });
    expect(await loadProjectShell(client, "stranger", "project-1")).toMatchObject({ myRole: null, canEdit: false });
  });

  it("rethrows getProject failures so the route can show 404", async () => {
    use({ projects: [] });
    await expect(loadProjectShell(client, "u1", "missing")).rejects.toMatchObject({ status: 404 });
  });

  it("falls back to blank class names when Classroom is down", async () => {
    use({ projects: [buildProject()] }, false);
    server.use(http.get("/api/classroom/*", () => envelopeError(503, "SERVICE_UNAVAILABLE", "Lỗi")));
    expect(await loadProjectShell(client, "u1", "project-1")).toMatchObject({ classCode: "", courseCode: "", groupName: "" });
  });
});

describe("loadGroupProjects", () => {
  it("indexes projects by group and keeps partial", async () => {
    use({
      projects: [buildProject({ id: "a", classroom_group_id: "g1" }), buildProject({ id: "b", classroom_group_id: "g2" })],
      partial: true,
    });
    const { byGroup, partial } = await loadGroupProjects(client);
    expect([...byGroup.keys()].sort()).toEqual(["g1", "g2"]);
    expect(partial).toBe(true);
  });
});
