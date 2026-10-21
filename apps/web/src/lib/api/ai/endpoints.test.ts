import { describe, expect, it } from "vitest";

import type { AiDecompositionRequest } from "@/lib/api/ai/dto";
import { runAiRequest } from "@/lib/api/ai/endpoints";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { server } from "@/mocks/server";
import { aiHandlers, buildAiSubtask, type AiCall, type AiFixture } from "@/test/aiHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

const body: AiDecompositionRequest = {
  intent: "task_decomposition",
  target: { type: "task", id: "task-1" },
  input: { task_description: "Làm tính năng" },
};

const instant = () => Promise.resolve();

function use(fixture: AiFixture) {
  const calls: AiCall[] = [];
  server.use(...aiHandlers({ decomposition: { subtasks: [buildAiSubtask()], warnings: [] }, ...fixture, calls }));
  return calls;
}

describe("runAiRequest", () => {
  it("returns the result of a synchronous 200 with one call and the idempotency key", async () => {
    const calls = use({});
    const run = await runAiRequest(client, body, { idempotencyKey: "key-1", sleep: instant });

    expect(run.result).toEqual({ subtasks: [buildAiSubtask()], warnings: [] });
    expect(run.context.fingerprint).toBe("fp");
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ method: "POST", idempotencyKey: "key-1", body });
  });

  it("polls a 202 until the request succeeds", async () => {
    const calls = use({ mode: "async" });
    const run = await runAiRequest(client, body, { idempotencyKey: "key-2", sleep: instant });

    expect(run.requestId).toBe("ai-1");
    expect(calls.map((call) => call.method)).toEqual(["POST", "GET", "GET"]);
  });

  it("throws an ApiError carrying the code when the request finished as failed", async () => {
    use({ failedResult: { code: "PROVIDER_UNAVAILABLE", message: "Nhà cung cấp lỗi" } });

    const error = await runAiRequest(client, body, { idempotencyKey: "k", sleep: instant }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "PROVIDER_UNAVAILABLE", message: "Nhà cung cấp lỗi" });
  });

  it("keeps the code, message and Retry-After of an HTTP error", async () => {
    use({ failWith: { status: 429, code: "RATE_LIMITED", message: "Quá nhiều", retryAfter: "9" } });

    const error = await runAiRequest(client, body, { idempotencyKey: "k", sleep: instant }).catch((e: unknown) => e);

    expect(error).toMatchObject({ status: 429, code: "RATE_LIMITED", message: "Quá nhiều", retryAfterSeconds: 9 });
  });

  it("stops polling once aborted", async () => {
    const calls = use({ mode: "async" });
    const controller = new AbortController();
    const abortingSleep = () => {
      controller.abort();
      return Promise.resolve();
    };

    const error = await runAiRequest(client, body, {
      idempotencyKey: "k",
      signal: controller.signal,
      sleep: abortingSleep,
    }).catch((e: unknown) => e);

    expect(error).toMatchObject({ name: "AbortError" });
    expect(calls.filter((call) => call.method === "GET").length).toBeLessThanOrEqual(1);
  });

  it("gives up with WORKFLOW_TIMEOUT after the maximum wait", async () => {
    use({ mode: "async" });
    let clock = 0;
    const now = () => clock;
    const sleep = () => {
      clock += 40_000;
      return Promise.resolve();
    };

    const error = await runAiRequest(client, body, { idempotencyKey: "k", sleep, now, maxWaitMs: 30_000 }).catch(
      (e: unknown) => e,
    );

    expect(error).toMatchObject({ status: 504, code: "WORKFLOW_TIMEOUT" });
  });
});
