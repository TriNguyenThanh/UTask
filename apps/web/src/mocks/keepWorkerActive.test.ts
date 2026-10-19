import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  keepMockWorkerActive,
  MOCK_ACTIVATE_MESSAGE,
  REACTIVATE_INTERVAL_MS,
} from "@/mocks/keepWorkerActive";

describe("keepMockWorkerActive", () => {
  const postMessage = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    postMessage.mockClear();
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        controller: { postMessage },
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    Reflect.deleteProperty(navigator, "serviceWorker");
  });

  it("re-sends activation on start, on interval, and on tab visible; stops after cleanup", () => {
    const stop = keepMockWorkerActive();
    expect(postMessage).toHaveBeenCalledTimes(1);
    expect(postMessage).toHaveBeenCalledWith(MOCK_ACTIVATE_MESSAGE);

    vi.advanceTimersByTime(REACTIVATE_INTERVAL_MS * 2);
    expect(postMessage).toHaveBeenCalledTimes(3);

    document.dispatchEvent(new Event("visibilitychange"));
    expect(postMessage).toHaveBeenCalledTimes(4);

    stop();
    vi.advanceTimersByTime(REACTIVATE_INTERVAL_MS * 3);
    expect(postMessage).toHaveBeenCalledTimes(4);
  });

  it("is a no-op without service worker support", () => {
    Reflect.deleteProperty(navigator, "serviceWorker");
    expect(() => keepMockWorkerActive()()).not.toThrow();
  });
});
