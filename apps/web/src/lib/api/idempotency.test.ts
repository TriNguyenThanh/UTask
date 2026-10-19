import { describe, expect, it } from "vitest";

import { newIdempotencyKey } from "@/lib/api/idempotency";

describe("newIdempotencyKey", () => {
  it("returns a UUID and a fresh value per call", () => {
    const first = newIdempotencyKey();
    const second = newIdempotencyKey();

    expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(second).not.toBe(first);
  });
});
