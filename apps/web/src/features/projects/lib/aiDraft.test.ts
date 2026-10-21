import { describe, expect, it } from "vitest";

import { markCreated, pendingItems, setSelected, setTitle, toDraft } from "@/features/projects/lib/aiDraft";

const sources = [{ title: "  Một " }, { title: "Hai" }, { title: "Ba" }];

describe("toDraft", () => {
  it("selects every item, trims titles and gives distinct keys", () => {
    const draft = toDraft(sources);

    expect(draft.map((item) => item.title)).toEqual(["Một", "Hai", "Ba"]);
    expect(draft.every((item) => item.selected && !item.created)).toBe(true);
    expect(new Set(draft.map((item) => item.key)).size).toBe(3);
  });

  it("cuts titles to 300 characters", () => {
    expect(toDraft([{ title: "x".repeat(400) }])[0].title).toHaveLength(300);
  });
});

describe("setTitle", () => {
  it("changes the title and the idempotency key of a pending item only", () => {
    const draft = toDraft(sources);
    const next = setTitle(draft, 1, "Mới");

    expect(next[1].title).toBe("Mới");
    expect(next[1].key).not.toBe(draft[1].key);
    expect(next[1].id).toBe(draft[1].id);
    expect(next[0]).toBe(draft[0]);
  });

  it("ignores an item that was already created", () => {
    const created = markCreated(toDraft(sources), []);
    const draft = markCreated(created, [created[0].key]);

    expect(setTitle(draft, 0, "Mới")[0]).toBe(draft[0]);
    expect(setSelected(draft, 0, false)[0]).toBe(draft[0]);
  });
});

describe("pendingItems", () => {
  it("drops unselected, created and blank-title items", () => {
    let draft = toDraft(sources);
    draft = setSelected(draft, 0, false);
    draft = setTitle(draft, 1, "   ");
    draft = markCreated(draft, [draft[2].key]);

    expect(pendingItems(draft)).toEqual([]);
    expect(pendingItems(setTitle(draft, 1, "Ổn"))).toHaveLength(1);
  });
});
