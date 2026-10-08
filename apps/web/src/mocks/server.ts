import { setupServer } from "msw/node";

import { createMemoryRepository } from "@/mocks/data/storage";
import { createMockHandlers } from "@/mocks/handlers";
import type { MockScenario } from "@/mocks/scenarios";

export function handlersForScenario(scenario: MockScenario = "default") {
  return createMockHandlers(scenario, createMemoryRepository(scenario));
}

export const server = setupServer(...handlersForScenario());
