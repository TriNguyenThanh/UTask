import { describe, expect, it } from "vitest";

import { instructorNameOf, membershipOf, toCourseDetail, toCourseEnrollment, toTeamMember } from "@/lib/api/classroom/adapters";
import { buildClass, buildCourse, buildGroup, buildMember, buildTeacher } from "@/test/classroomHandlers";
import type { PublicUserDto } from "@/lib/api/identity/dto";

function user(id: string, display_name: string): PublicUserDto {
  return { id, email: `${id}@x.vn`, student_id: null, display_name, avatar_url: null, bio: null, roles: [], account_status: "ACTIVE" };
}

describe("membershipOf", () => {
  const group = buildGroup();

  it("is none without a group", () => {
    expect(membershipOf("user-1", null)).toEqual({ status: "none" });
  });

  it("is assigned as member", () => {
    expect(membershipOf("user-1", { group, members: [buildMember()] })).toEqual({
      status: "assigned",
      teamId: "group-1",
      teamName: "Nhóm 1",
      role: "member",
    });
  });

  it("is assigned as leader when the active member row is LEADER", () => {
    const mine = { group, members: [buildMember({ role: "LEADER" }), buildMember({ user_id: "other", id: "m2" })] };
    expect(membershipOf("user-1", mine)).toMatchObject({ status: "assigned", role: "leader" });
  });

  it("never marks a LEFT member row as leader", () => {
    const mine = { group, members: [buildMember({ role: "LEADER", status: "LEFT" })] };
    expect(membershipOf("user-1", mine)).toMatchObject({ role: "member" });
  });
});

describe("toCourseEnrollment", () => {
  it("joins the course code and uses class name/term", () => {
    const result = toCourseEnrollment(buildClass(), buildCourse(), { status: "none" });
    expect(result).toMatchObject({
      courseId: "class-1",
      courseCode: "SE100",
      courseName: "Đồ án phần mềm",
      semester: "HK1 2026–2027",
      projectId: null,
      teamFormation: { mode: "join-code", registrationDeadline: null },
    });
  });

  it("marks formation closed for archived classes and locked grouping", () => {
    const none = { status: "none" } as const;
    expect(toCourseEnrollment(buildClass(), buildCourse(), none).formationClosed).toBe(false);
    expect(toCourseEnrollment(buildClass({ status: "ARCHIVED" }), buildCourse(), none).formationClosed).toBe(true);
    expect(toCourseEnrollment(buildClass({ grouping_phase: "LOCKED" }), buildCourse(), none).formationClosed).toBe(true);
  });

  it("falls back to the class code and class name when the course is not listed", () => {
    const result = toCourseEnrollment(buildClass(), undefined, { status: "none" });
    expect(result.courseCode).toBe("SE100.N11");
    expect(result.courseName).toBe(buildClass().name);
  });

  it("uses the subject name, not the class name, as courseName", () => {
    const result = toCourseEnrollment(buildClass({ name: "Lớp N11" }), buildCourse({ name: "Công nghệ phần mềm" }), { status: "none" });
    expect(result.courseName).toBe("Công nghệ phần mềm");
  });
});

describe("instructorNameOf", () => {
  const users = [user("t1", "Cô Lan"), user("t2", "Thầy Minh")];

  it("lists PRIMARY first and skips LEFT teachers", () => {
    const teachers = [
      buildTeacher({ id: "a", user_id: "t2", role: "CO_TEACHER" }),
      buildTeacher({ id: "b", user_id: "t1", role: "PRIMARY" }),
      buildTeacher({ id: "c", user_id: "gone", status: "LEFT" }),
    ];
    expect(instructorNameOf(teachers, users)).toBe("Cô Lan, Thầy Minh");
  });

  it("skips teachers whose profile is unknown and is empty without users", () => {
    expect(instructorNameOf([buildTeacher({ user_id: "unknown" })], users)).toBe("");
    expect(instructorNameOf([buildTeacher()], [])).toBe("");
  });
});

describe("toTeamMember", () => {
  it("reads the profile and tolerates an empty one", () => {
    expect(toTeamMember(buildMember({ role: "LEADER" }))).toMatchObject({
      displayName: "Nguyễn Văn An",
      studentId: "6451071001",
      email: "an@st.edu.vn",
      role: "leader",
      skill: "",
      responsibility: "",
    });
    expect(toTeamMember(buildMember({ profile: {} }))).toMatchObject({ displayName: "", studentId: "", email: "" });
  });
});

describe("toCourseDetail", () => {
  const base = { userId: "user-1", cls: buildClass(), course: buildCourse(), instructorName: "Cô Lan" };

  it("without a group: none, no formation data, no class size, no topic", () => {
    const detail = toCourseDetail({ ...base, mine: null });
    expect(detail).toMatchObject({
      membership: { status: "none" },
      team: null,
      formation: null,
      classSize: null,
      teamSize: { min: 3, max: 5 },
      instructorName: "Cô Lan",
      teamFormation: { selfCreateAllowed: true },
    });
  });

  it("with a group: members mapped, leader flag, topic and repository empty", () => {
    const mine = {
      group: buildGroup(),
      members: [buildMember({ role: "LEADER" }), buildMember({ id: "m2", user_id: "u2", role: "MEMBER" }), buildMember({ id: "m3", user_id: "u3", status: "LEFT" })],
    };
    const detail = toCourseDetail({ ...base, mine });

    expect(detail.team).toMatchObject({ teamName: "Nhóm 1", isLeader: true, memberCount: 2, maxMembers: 5, topic: null, repository: null });
    expect(detail.team?.members.map((m) => m.userId)).toEqual(["user-1", "u2"]);
    expect(detail.formation).toBeNull();
  });

  it("disallows self-create when grouping is locked or the class is closed", () => {
    expect(toCourseDetail({ ...base, cls: buildClass({ grouping_phase: "LOCKED" }), mine: null }).teamFormation.selfCreateAllowed).toBe(false);
    expect(toCourseDetail({ ...base, cls: buildClass({ status: "CLOSED" }), mine: null }).teamFormation.selfCreateAllowed).toBe(false);
  });
});
