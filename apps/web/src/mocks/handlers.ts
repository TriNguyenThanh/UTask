import { createAuthHandlers } from "@/mocks/handlers/auth";
import { createMyWorkHandlers } from "@/mocks/handlers/myWork";
import { createStudentFlowHandlers } from "@/mocks/handlers/studentFlow";
import type { MockRepository } from "@/mocks/data/storage";
import type { MockScenario } from "@/mocks/scenarios";
import type { HttpHandler } from "msw";

export function createMockHandlers(scenario: MockScenario, repository: MockRepository): HttpHandler[] {
  return [
    ...createAuthHandlers(scenario, repository),
    ...createMyWorkHandlers(scenario, repository),
    ...createStudentFlowHandlers(scenario, repository),
  ];
}