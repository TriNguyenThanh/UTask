import type { HttpHandler } from "msw";

import { projectHandlers, type ProjectFixture } from "@/test/workHandlers.projects";
import { taskHandlers, type TaskFixture } from "@/test/workHandlers.tasks";

export { buildProject, buildProjectMember } from "@/test/workHandlers.projects";
export {
  buildDefaultStates,
  buildEpic,
  buildLabel,
  buildSprint,
  buildState,
  buildTask,
} from "@/test/workHandlers.tasks";
export type { WorkCall, WorkError } from "@/test/workHandlers.shared";

export type WorkFixture = ProjectFixture & TaskFixture;

/** `projects` là bắt buộc (nhóm Project); các nhóm khác bỏ trống thì trả danh sách rỗng. */
export function workHandlers(fixture: WorkFixture): HttpHandler[] {
  return [...projectHandlers(fixture), ...taskHandlers(fixture)];
}
