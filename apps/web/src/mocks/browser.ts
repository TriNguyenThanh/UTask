import { setupWorker } from "msw/browser";

import { createBrowserRepository } from "@/mocks/data/storage";
import { createMockHandlers } from "@/mocks/handlers";
import { resolveMockScenario } from "@/mocks/scenarios";

const scenario = resolveMockScenario(import.meta.env.VITE_MOCK_SCENARIO);
const repository = createBrowserRepository(scenario);

export const worker = setupWorker(...createMockHandlers(scenario, repository));
