import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";

import { handlersForScenario, server } from "@/mocks/server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => vi.stubEnv("VITE_ENABLE_MOCKS", "true"));
/** jsdom giữ cookie giữa các test; phiên khôi phục từ cookie của test trước sẽ làm test sau lệch. */
function clearCookies() {
  for (const entry of document.cookie.split("; ")) {
    document.cookie = `${entry.split("=")[0]}=; Max-Age=0; Path=/`;
  }
}

afterEach(() => {
  cleanup();
  clearCookies();
  server.resetHandlers(...handlersForScenario());
  vi.unstubAllEnvs();
});
afterAll(() => server.close());
