import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { usersBatch } from "@/lib/api/identity/endpoints";
import { server } from "@/mocks/server";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

describe("usersBatch", () => {
  it("dedupes ids and splits calls at the backend limit of 100", async () => {
    const sizes: number[] = [];
    server.use(
      http.post("/api/auth/users/batch", async ({ request }) => {
        const { user_ids } = (await request.json()) as { user_ids: string[] };
        sizes.push(user_ids.length);
        const users = user_ids.map((id) => ({ id }));
        return HttpResponse.json({ success: true, message: "OK", data: { users }, meta: null, error: null });
      }),
    );
    const ids = Array.from({ length: 150 }, (_, index) => `u${index}`);
    const users = await usersBatch(client, [...ids, "u0", "u1"]);

    expect(sizes).toEqual([100, 50]);
    expect(users).toHaveLength(150);
  });

  it("makes no request for an empty list", async () => {
    expect(await usersBatch(client, [])).toEqual([]);
  });
});
