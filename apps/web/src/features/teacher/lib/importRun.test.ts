import { describe, expect, it } from "vitest";

import type { ImportRow } from "@/features/teacher/lib/csvImport";
import type { ImportResultDto, ImportRowResultDto } from "@/lib/api/classroom/dto";
import { chunk, describeResult, mergeSummaries, reasonLabel, sendableRows, toStudentRow } from "@/features/teacher/lib/importRun";

function row(overrides: Partial<ImportRow> = {}): ImportRow {
  return { rowNumber: 2, studentId: "", email: "", firstName: "", lastName: "", issues: [], ...overrides };
}

function result(overrides: Partial<ImportRowResultDto> = {}): ImportRowResultDto {
  return {
    row_number: 2,
    user_id: "u1",
    email: "a@st.edu.vn",
    student_id: null,
    account_status: "ACTIVE",
    account_result: "EXISTING",
    reason: null,
    enrollment_id: "e1",
    enrollment_result: "ENROLLED",
    ...overrides,
  };
}

describe("sendableRows", () => {
  it("drops rows with an error-level issue and keeps warnings", () => {
    const bad = row({ rowNumber: 3, issues: [{ code: "invalid-email", level: "error", message: "x" }] });
    const warned = row({ rowNumber: 4, issues: [{ code: "duplicate-in-file", level: "warning", message: "x" }] });
    expect(sendableRows([row(), bad, warned]).map((entry) => entry.rowNumber)).toEqual([2, 4]);
  });
});

describe("toStudentRow", () => {
  it("keeps the row number and sends only keys that have a value", () => {
    expect(toStudentRow(row({ rowNumber: 7, email: "a@st.edu.vn" }))).toEqual({ row_number: 7, email: "a@st.edu.vn" });
    expect(toStudentRow(row({ studentId: "6451071001", firstName: "An", lastName: "Nguyễn" }))).toEqual({
      row_number: 2,
      student_id: "6451071001",
      first_name: "An",
      last_name: "Nguyễn",
    });
  });
});

describe("chunk", () => {
  it("splits into batches of the size, the last one shorter, and returns nothing for no items", () => {
    expect(chunk(Array.from({ length: 250 }, (_, index) => index), 100).map((batch) => batch.length)).toEqual([100, 100, 50]);
    expect(chunk([], 100)).toEqual([]);
    expect(chunk([1, 2, 3], 3)).toEqual([[1, 2, 3]]);
  });
});

describe("mergeSummaries", () => {
  it("adds every counter across batches", () => {
    const summary = (enrolled: number, failed: number): ImportResultDto["summary"] => ({
      total_records: enrolled + failed,
      enrolled,
      already_enrolled: 1,
      failed,
      created_accounts: 2,
      existing_accounts: 3,
      flagged: 0,
      duplicates: failed,
    });
    const merged = mergeSummaries([
      { summary: summary(98, 2), results: [] },
      { summary: summary(50, 0), results: [] },
    ]);
    expect(merged).toEqual({ total_records: 150, enrolled: 148, already_enrolled: 2, failed: 2, created_accounts: 4, existing_accounts: 6, flagged: 0, duplicates: 2 });
    expect(mergeSummaries([]).total_records).toBe(0);
  });
});

describe("reasonLabel and describeResult", () => {
  it("explains known reasons, shows an unknown code verbatim and handles a missing one", () => {
    expect(reasonLabel("FLAGGED_ROLE_CONFLICT")).toContain("giảng viên");
    expect(reasonLabel("SOMETHING_NEW")).toBe("Lý do: SOMETHING_NEW");
    expect(reasonLabel(null)).toBe("Không rõ lý do.");
  });

  it("tells a new account, an existing one, an already-enrolled one and a refusal apart", () => {
    expect(describeResult(result({ account_result: "CREATED" }))).toMatchObject({ tone: "success", label: expect.stringContaining("Tạo tài khoản mới") });
    expect(describeResult(result())).toMatchObject({ tone: "success", detail: null });
    expect(describeResult(result({ enrollment_result: "ALREADY_ENROLLED" }))).toMatchObject({ tone: "neutral", label: "Đã thuộc lớp" });
    const refused = describeResult(result({ enrollment_result: "FAILED", account_result: "FAILED", reason: "STUDENT_ID_NOT_FOUND" }));
    expect(refused.tone).toBe("problem");
    expect(refused.detail).toContain("MSSV");
  });
});
