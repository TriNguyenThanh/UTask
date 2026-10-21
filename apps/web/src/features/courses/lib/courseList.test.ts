import { describe, expect, it } from "vitest";

import {
  courseCtaLabel,
  matchesFilters,
  membershipBadge,
  summarizeCourses,
} from "@/features/courses/lib/courseList";
import type { CourseEnrollment } from "@/features/my-work/types";

function enrollment(overrides: Partial<CourseEnrollment> = {}): CourseEnrollment {
  return {
    courseId: "c1",
    courseCode: "SE100",
    courseName: "Lớp 1",
    semester: "HK1 2026–2027",
    teamFormation: { mode: "join-code", registrationDeadline: null },
    projectId: null,
    membership: { status: "none" },
    ...overrides,
  };
}

describe("closed team formation", () => {
  const open = enrollment();
  const closed = enrollment({ courseId: "c2", formationClosed: true });

  it("keeps the call to action for open classes", () => {
    expect(membershipBadge({ status: "none" }).label).toBe("Cần lập nhóm");
    expect(courseCtaLabel({ status: "none" })).toBe("Thành lập nhóm");
  });

  it("does not ask a student in a closed class to form a team", () => {
    expect(membershipBadge({ status: "none" }, true).label).toBe("Đã khóa lập nhóm");
    expect(courseCtaLabel({ status: "none" }, true)).toBe("Xem lớp");
  });

  it("leaves closed classes out of the need-a-team filter but keeps them under all", () => {
    expect(matchesFilters(open, "", "none")).toBe(true);
    expect(matchesFilters(closed, "", "none")).toBe(false);
    expect(matchesFilters(closed, "", "all")).toBe(true);
  });

  it("counts closed classes only in the total", () => {
    expect(summarizeCourses([open, closed])).toEqual({ all: 2, none: 1, pending: 0, assigned: 0 });
  });

  it("still shows team status for a student who already has a team in a closed class", () => {
    const team = enrollment({
      formationClosed: true,
      membership: { status: "assigned", teamId: "t", teamName: "N", role: "leader" },
    });
    expect(membershipBadge(team.membership, team.formationClosed).label).toBe("Trưởng nhóm");
    expect(summarizeCourses([team]).assigned).toBe(1);
  });
});
