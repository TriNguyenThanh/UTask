import { useOutletContext } from "react-router-dom";

import type { TeacherCourseDetail } from "@/lib/api/teacherFlow";

/** The class loaded by `TeacherCourseLayout`, shared with its tab routes. */
export function useTeacherCourseContext(): TeacherCourseDetail {
  return useOutletContext<TeacherCourseDetail>();
}
