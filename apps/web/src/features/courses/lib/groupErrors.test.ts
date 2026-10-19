import { describe, expect, it } from "vitest";

import { groupErrorMessage, isConflict, STALE_GROUP_MESSAGE } from "@/features/courses/lib/groupErrors";
import { ApiError } from "@/lib/api/errors";

const err = (status: number, code: string | null, message: string) => new ApiError({ status, code, message });

describe("groupErrorMessage", () => {
  it("uses the generic stale message for a version conflict", () => {
    expect(groupErrorMessage(err(409, "VERSION_CONFLICT", "Nhóm học tập đã thay đổi."))).toBe(STALE_GROUP_MESSAGE);
  });

  it("keeps the server message for other business conflicts and errors", () => {
    expect(groupErrorMessage(err(409, "GROUP_FULL", "Nhóm đã đủ số thành viên tối đa."))).toBe("Nhóm đã đủ số thành viên tối đa.");
    expect(groupErrorMessage(err(403, "PERMISSION_DENIED", "Bạn không có quyền."))).toBe("Bạn không có quyền.");
  });

  it("falls back for non-API errors", () => {
    expect(groupErrorMessage(new Error("boom"))).toMatch(/Không thể thực hiện/);
  });
});

describe("isConflict", () => {
  it("is true only for HTTP 409 API errors", () => {
    expect(isConflict(err(409, "GROUP_FULL", "x"))).toBe(true);
    expect(isConflict(err(404, null, "x"))).toBe(false);
    expect(isConflict(new Error("409"))).toBe(false);
  });
});
