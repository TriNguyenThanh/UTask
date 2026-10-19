import { describe, expect, it } from "vitest";

import { historyCourseDetailFor, historyEnrollmentsFor } from "@/mocks/data/courseHistory";
import { LEADER_ID, MEMBER_ID, TEACHER_ID } from "@/mocks/data/database";

describe("past-term course history", () => {
  it("keeps the role per course, so one account is leader in one course and member in another", () => {
    const roles = historyEnrollmentsFor(LEADER_ID).map((enrollment) =>
      enrollment.membership.status === "assigned" ? enrollment.membership.role : null,
    );
    expect(roles).toContain("leader");
    expect(roles).toContain("member");
  });

  it("serves a read-only detail that agrees with the enrollment, and nothing to other accounts", () => {
    for (const enrollment of historyEnrollmentsFor(MEMBER_ID)) {
      const detail = historyCourseDetailFor(enrollment.courseId, MEMBER_ID);
      expect(detail?.semester).toBe(enrollment.semester);
      expect(detail?.membership).toEqual(enrollment.membership);
      expect(detail?.team?.projectId).toBeNull();
      expect(detail?.team?.members[0].userId).toBe(MEMBER_ID);
    }
    expect(historyEnrollmentsFor(TEACHER_ID)).toEqual([]);
    expect(historyCourseDetailFor("course-hist-se210", TEACHER_ID)).toBeNull();
    expect(historyCourseDetailFor("course-se330", MEMBER_ID)).toBeNull();
  });
});
