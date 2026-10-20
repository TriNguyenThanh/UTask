import { describe, expect, it } from "vitest";

import { validateLabelForm } from "@/features/projects/lib/labelForm";

describe("validateLabelForm", () => {
  it("accepts a trimmed name with a #RRGGBB colour", () => {
    expect(validateLabelForm({ name: " ui ", color: "#0A1b2C" })).toBeNull();
  });

  it("rejects an empty or overlong name", () => {
    expect(validateLabelForm({ name: "  ", color: "#000000" })).toMatch(/không được để trống/);
    expect(validateLabelForm({ name: "x".repeat(51), color: "#000000" })).toMatch(/50/);
  });

  it("rejects colours that are not #RRGGBB", () => {
    for (const color of ["red", "#fff", "#12345G", "123456"]) {
      expect(validateLabelForm({ name: "ui", color })).toMatch(/#RRGGBB/);
    }
  });
});
