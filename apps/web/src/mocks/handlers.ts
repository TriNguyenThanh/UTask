import { isRealService } from "@/lib/config/services";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { createMyWorkHandlers } from "@/mocks/handlers/myWork";
import { createStudentFlowHandlers } from "@/mocks/handlers/studentFlow";
import { createTeacherFlowHandlers } from "@/mocks/handlers/teacherFlow";
import type { MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import type { HttpHandler } from "msw";

export function createMockHandlers(scenario: MockScenario, repository: MockRepository): HttpHandler[] {
  return [
    // Service thật không còn handler mock: lỗi của service thật không bao giờ rơi về MSW.
    ...(isRealService("auth") ? [] : createAuthHandlers(scenario, repository)),
    ...createMyWorkHandlers(scenario, repository),
    ...createStudentFlowHandlers(scenario, repository),
    ...createTeacherFlowHandlers(scenario, repository),
  ];
}
