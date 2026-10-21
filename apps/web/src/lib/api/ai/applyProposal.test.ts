import { describe, expect, it, vi } from "vitest";

import { applySequentially } from "@/lib/api/ai/applyProposal";

const items = [
  { key: "k1", input: "a" },
  { key: "k2", input: "b" },
  { key: "k3", input: "c" },
];

describe("applySequentially", () => {
  it("creates every item in order with its own key", async () => {
    const create = vi.fn().mockResolvedValue(undefined);
    const progress = vi.fn();

    const outcome = await applySequentially(items, create, progress);

    expect(create.mock.calls).toEqual([["a", "k1"], ["b", "k2"], ["c", "k3"]]);
    expect(outcome).toEqual({ createdKeys: ["k1", "k2", "k3"], failure: null });
    expect(progress.mock.calls).toEqual([[1, 3], [2, 3], [3, 3]]);
  });

  it("stops at the first failure and reports what was created", async () => {
    const boom = new Error("boom");
    const create = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(boom);

    const outcome = await applySequentially(items, create);

    expect(outcome).toEqual({ createdKeys: ["k1"], failure: { key: "k2", error: boom } });
    expect(create).toHaveBeenCalledTimes(2);
  });

  it("does nothing for an empty list", async () => {
    const create = vi.fn();
    expect(await applySequentially([], create)).toEqual({ createdKeys: [], failure: null });
    expect(create).not.toHaveBeenCalled();
  });
});
