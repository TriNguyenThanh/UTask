import { describe, expect, it } from "vitest";

import { initialsOf, personName, validateCommentText, COMMENT_MAX_LENGTH } from "@/features/projects/lib/comments";

describe("validateCommentText", () => {
  it("rejects blank text and accepts up to the exact limit", () => {
    expect(validateCommentText("")).toMatch(/Nhập/);
    expect(validateCommentText("   \n ")).toMatch(/Nhập/);
    expect(validateCommentText("Xong")).toBeNull();
    expect(validateCommentText("a".repeat(COMMENT_MAX_LENGTH))).toBeNull();
    expect(validateCommentText("a".repeat(COMMENT_MAX_LENGTH + 1))).toMatch(/dài quá/);
  });
});

describe("personName", () => {
  const people = [{ userId: "u1", name: "Đặng Thảo Linh" }, { userId: "u2", name: "" }];

  it("prefers the server name, then the known member, then a placeholder", () => {
    expect(personName("u1", people, "Tên từ server")).toBe("Tên từ server");
    expect(personName("u1", people, "  ")).toBe("Đặng Thảo Linh");
    expect(personName("u2", people)).toBe("Chưa rõ tên");
    expect(personName("ghost", people)).toBe("Chưa rõ tên");
    expect(personName(null, people)).toBe("Chưa rõ tên");
  });
});

describe("initialsOf", () => {
  it("uses first and last word, or the first two letters of a single word", () => {
    expect(initialsOf("Đặng Thảo Linh")).toBe("ĐL");
    expect(initialsOf("Nam")).toBe("NA");
    expect(initialsOf("  ")).toBe("?");
  });
});
