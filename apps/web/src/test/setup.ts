import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

import { handlersForScenario, server } from "@/mocks/server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => vi.stubEnv("VITE_ENABLE_MOCKS", "true"));
afterEach(() => {
  cleanup();
  server.resetHandlers(...handlersForScenario());
  vi.unstubAllEnvs();
});
afterAll(() => server.close());
