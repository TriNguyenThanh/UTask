import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function setup(response: Response | Error, token: string | null = null) {
  const fetchMock = vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response.clone()),
  );
  vi.stubGlobal("fetch", fetchMock);
  const onUnauthorized = vi.fn();
  const client = createApiClient({ baseUrl: "", getAccessToken: () => token, onUnauthorized });
  return { client, fetchMock, onUnauthorized };
}

async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("Expected request to fail");
}

afterEach(() => vi.unstubAllGlobals());

describe("createApiClient", () => {
  it("sends credentials, bearer token and JSON body", async () => {
    const { client, fetchMock } = setup(jsonResponse({ ok: true }), "tok");

    await client.request("/api/x", { method: "POST", body: { a: 1 } });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/x");
    expect(init?.credentials).toBe("include");
    expect(init?.body).toBe('{"a":1}');
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("sends Idempotency-Key only when provided", async () => {
    const { client, fetchMock } = setup(jsonResponse({ ok: true }));

    await client.request("/api/x", { method: "POST", idempotencyKey: "key-1" });
    await client.request("/api/x", { method: "POST" });

    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Idempotency-Key")).toBe("key-1");
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).has("Idempotency-Key")).toBe(false);
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("idempotencyKey");
  });

  it("request returns the raw body and undefined for 204", async () => {
    const raw = setup(jsonResponse({ id: 7 }));
    await expect(raw.client.request("/api/x")).resolves.toEqual({ id: 7 });

    const empty = setup(new Response(null, { status: 204 }));
    await expect(empty.client.request("/api/x")).resolves.toBeUndefined();
  });
});

describe("requestEnvelope", () => {
  it("unwraps data, meta and message", async () => {
    const { client } = setup(
      jsonResponse({ success: true, message: "OK", data: [1, 2], meta: { pagination: { has_next: false } } }),
    );

    await expect(client.requestEnvelope("/api/x")).resolves.toEqual({
      data: [1, 2],
      meta: { pagination: { has_next: false } },
      message: "OK",
    });
  });

  it("defaults meta to null and message to empty", async () => {
    const { client } = setup(jsonResponse({ success: true, data: { a: 1 } }));

    await expect(client.requestEnvelope("/api/x")).resolves.toEqual({ data: { a: 1 }, meta: null, message: "" });
  });

  it("accepts 204 without a body", async () => {
    const { client } = setup(new Response(null, { status: 204 }));

    await expect(client.requestEnvelope("/api/x")).resolves.toEqual({ data: undefined, meta: null, message: "" });
  });

  it("rejects a 2xx payload that is not an envelope", async () => {
    const { client } = setup(jsonResponse({ id: 1 }));

    const error = await catchApiError(client.requestEnvelope("/api/x"));
    expect(error.status).toBe(200);
    expect(error.message).toBe("Phản hồi máy chủ không đúng định dạng.");
  });

  it("rejects a 2xx non-JSON body", async () => {
    const { client } = setup(new Response("<html></html>", { status: 200 }));

    const error = await catchApiError(client.requestEnvelope("/api/x"));
    expect(error.message).toBe("Phản hồi máy chủ không đúng định dạng.");
  });
});

describe("error mapping", () => {
  it("maps envelope errors to code, details, fieldErrors and message", async () => {
    const { client } = setup(
      jsonResponse(
        {
          success: false,
          message: "Dữ liệu không hợp lệ.",
          data: null,
          meta: null,
          error: {
            code: "VALIDATION_ERROR",
            details: [
              { field: "email", issue: "Sai định dạng." },
              { field: "email", issue: "Đã tồn tại." },
              { issue: "Lỗi chung." },
              { bogus: true },
            ],
          },
        },
        { status: 400, headers: { "Content-Type": "application/json", "x-request-id": "req-1" } },
      ),
    );

    const error = await catchApiError(client.requestEnvelope("/api/x"));
    expect(error.status).toBe(400);
    expect(error.code).toBe("VALIDATION_ERROR");
    expect(error.message).toBe("Dữ liệu không hợp lệ.");
    expect(error.fieldErrors).toEqual({ email: ["Sai định dạng.", "Đã tồn tại."] });
    expect(error.details).toEqual([
      { field: "email", issue: "Sai định dạng." },
      { field: "email", issue: "Đã tồn tại." },
      { issue: "Lỗi chung." },
    ]);
    expect(error.requestId).toBe("req-1");
  });

  it("reads Retry-After seconds on 429 and ignores non-numeric values", async () => {
    const limited = setup(
      jsonResponse(
        { success: false, message: "Quá nhiều.", error: { code: "RATE_LIMIT_EXCEEDED", details: [] } },
        { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "900" } },
      ),
    );
    expect((await catchApiError(limited.client.request("/api/x"))).retryAfterSeconds).toBe(900);

    const dated = setup(
      jsonResponse({ detail: "x" }, { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" } }),
    );
    expect((await catchApiError(dated.client.request("/api/x"))).retryAfterSeconds).toBeNull();
  });

  it("keeps legacy detail and field-array payloads working", async () => {
    const detail = setup(jsonResponse({ detail: "Sai mật khẩu." }, { status: 400 }));
    const detailError = await catchApiError(detail.client.request("/api/x"));
    expect(detailError.message).toBe("Sai mật khẩu.");
    expect(detailError.code).toBeNull();
    expect(detailError.details).toEqual([]);
    expect(detailError.retryAfterSeconds).toBeNull();

    const fields = setup(jsonResponse({ email: ["Bắt buộc."] }, { status: 400 }));
    expect((await catchApiError(fields.client.request("/api/x"))).fieldErrors).toEqual({ email: ["Bắt buộc."] });
  });

  it("falls back to status messages for empty or non-JSON error bodies", async () => {
    const forbidden = setup(new Response("", { status: 403 }));
    expect((await catchApiError(forbidden.client.request("/api/x"))).message).toBe(
      "Bạn không có quyền thực hiện thao tác này.",
    );

    const missing = setup(new Response(null, { status: 404 }));
    expect((await catchApiError(missing.client.request("/api/x"))).message).toBe("Không tìm thấy dữ liệu yêu cầu.");

    const server = setup(new Response(null, { status: 502 }));
    expect((await catchApiError(server.client.request("/api/x"))).message).toBe("Yêu cầu không thành công.");

    const text = setup(new Response("Bad gateway", { status: 502 }));
    expect((await catchApiError(text.client.request("/api/x"))).message).toBe("Bad gateway");
  });

  it("reports network failures with status 0", async () => {
    const { client } = setup(new TypeError("Failed to fetch"));

    const error = await catchApiError(client.requestEnvelope("/api/x"));
    expect(error.status).toBe(0);
    expect(error.message).toBe("Không thể kết nối đến máy chủ.");
  });

  it("calls onUnauthorized once per token on 401", async () => {
    const { client, onUnauthorized } = setup(
      jsonResponse({ success: false, message: "x", error: { code: "INVALID_TOKEN" } }, { status: 401 }),
      "tok",
    );

    await catchApiError(client.requestEnvelope("/api/x"));
    await catchApiError(client.requestEnvelope("/api/x"));

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not call onUnauthorized for 401 without a token (login failure)", async () => {
    const { client, onUnauthorized } = setup(
      jsonResponse({ success: false, message: "x", error: { code: "INVALID_CREDENTIALS" } }, { status: 401 }),
    );

    await catchApiError(client.requestEnvelope("/api/x"));

    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
