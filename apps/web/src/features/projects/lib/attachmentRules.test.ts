import { describe, expect, it } from "vitest";

import {
  ATTACHMENT_MAX_BYTES,
  formatBytes,
  validateAttachmentFile,
} from "@/features/projects/lib/attachmentRules";

const ok = { name: "anh.png", size: 1024, type: "image/png" };

describe("validateAttachmentFile", () => {
  it("accepts a file within the limits, including the exact maximum size", () => {
    expect(validateAttachmentFile(ok)).toBeNull();
    expect(validateAttachmentFile({ ...ok, size: ATTACHMENT_MAX_BYTES })).toBeNull();
  });

  it("rejects empty, oversized, unsupported and long-named files", () => {
    expect(validateAttachmentFile({ ...ok, size: 0 })).toMatch(/rỗng/);
    expect(validateAttachmentFile({ ...ok, size: ATTACHMENT_MAX_BYTES + 1 })).toMatch(/vượt giới hạn/);
    expect(validateAttachmentFile({ ...ok, type: "application/x-msdownload" })).toMatch(/Chỉ nhận/);
    expect(validateAttachmentFile({ ...ok, type: "" })).toMatch(/Chỉ nhận/);
    expect(validateAttachmentFile({ ...ok, name: "a".repeat(256) })).toMatch(/Tên tệp/);
  });
});

describe("formatBytes", () => {
  it("picks a readable unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(ATTACHMENT_MAX_BYTES)).toBe("25.0 MB");
  });
});
