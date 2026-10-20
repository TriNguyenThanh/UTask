import { describe, expect, it } from "vitest";

import { myRoleOf, pickPrimaryProject, projectsByGroup, toProjectCards } from "@/lib/api/work/adapters";
import { buildClass, buildCourse } from "@/test/classroomHandlers";
import { buildProject, buildProjectMember } from "@/test/workHandlers";

describe("myRoleOf", () => {
  it("returns the role of the ACTIVE membership", () => {
    const members = [
      buildProjectMember({ user_id: "u1", role: "LEADER" }),
      buildProjectMember({ id: "pm-2", user_id: "u2", role: "MEMBER" }),
    ];
    expect(myRoleOf(members, "u1")).toBe("LEADER");
    expect(myRoleOf(members, "u2")).toBe("MEMBER");
  });

  it("is null for a user with only LEFT/REMOVED records or no record", () => {
    const members = [
      buildProjectMember({ user_id: "u1", status: "LEFT" }),
      buildProjectMember({ id: "pm-2", user_id: "u3", status: "REMOVED" }),
    ];
    expect(myRoleOf(members, "u1")).toBeNull();
    expect(myRoleOf(members, "u3")).toBeNull();
    expect(myRoleOf(members, "nobody")).toBeNull();
  });
});

describe("pickPrimaryProject", () => {
  it("skips archived projects and takes the earliest created", () => {
    const picked = pickPrimaryProject([
      buildProject({ id: "old-archived", created_at: "2026-01-01T00:00:00Z", archived_at: "2026-02-01T00:00:00Z" }),
      buildProject({ id: "later", created_at: "2026-03-01T00:00:00Z" }),
      buildProject({ id: "earlier", created_at: "2026-02-01T00:00:00Z" }),
    ]);
    expect(picked?.id).toBe("earlier");
  });

  it("breaks ties by ascending id", () => {
    const at = "2026-02-01T00:00:00Z";
    expect(pickPrimaryProject([buildProject({ id: "b", created_at: at }), buildProject({ id: "a", created_at: at })])?.id).toBe("a");
  });

  it("is null when every project is archived or the list is empty", () => {
    expect(pickPrimaryProject([buildProject({ archived_at: "2026-02-01T00:00:00Z" })])).toBeNull();
    expect(pickPrimaryProject([])).toBeNull();
  });
});

describe("projectsByGroup", () => {
  it("groups by classroom_group_id ordered by creation", () => {
    const map = projectsByGroup([
      buildProject({ id: "p2", classroom_group_id: "g1", created_at: "2026-02-01T00:00:00Z" }),
      buildProject({ id: "p3", classroom_group_id: "g2" }),
      buildProject({ id: "p1", classroom_group_id: "g1", created_at: "2026-01-01T00:00:00Z" }),
    ]);
    expect(map.get("g1")?.map((project) => project.id)).toEqual(["p1", "p2"]);
    expect(map.get("g2")?.map((project) => project.id)).toEqual(["p3"]);
    expect(map.get("g3")).toBeUndefined();
  });
});

describe("toProjectCards", () => {
  it("fills class, course, group and role from the context", () => {
    const [card] = toProjectCards([buildProject({ github_repo_name: "org/repo" })], {
      classes: new Map([["class-1", buildClass({ id: "class-1", code: "SE100.A", name: "Lớp A", course: "course-1" })]]),
      courses: new Map([["course-1", buildCourse({ id: "course-1", code: "SE100" })]]),
      groupNames: new Map([["group-1", "Nhóm 1"]]),
      roleByProject: new Map([["project-1", "LEADER"]]),
    });
    expect(card).toMatchObject({
      projectId: "project-1",
      classCode: "SE100.A",
      className: "Lớp A",
      courseCode: "SE100",
      groupName: "Nhóm 1",
      myRole: "LEADER",
      repository: "org/repo",
      archived: false,
    });
  });

  it("uses empty strings and null role instead of throwing when context is missing", () => {
    const [card] = toProjectCards([buildProject({ class_id: null, archived_at: "2026-02-01T00:00:00Z" })], {
      classes: new Map(),
      courses: new Map(),
      groupNames: new Map(),
      roleByProject: new Map(),
    });
    expect(card).toMatchObject({ classCode: "", className: "", courseCode: "", groupName: "", myRole: null, archived: true });
  });
});
