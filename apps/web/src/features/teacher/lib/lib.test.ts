import { afterEach, describe, expect, it, vi } from "vitest";

import { courseFormSchema, emptyCourseForm } from "@/features/teacher/lib/courseForm";
import {
  MAX_IMPORT_BYTES,
  MAX_IMPORT_ROWS,
  isSpreadsheetFile,
  parseCsv,
  readImportFile,
  type ImportPreview,
} from "@/features/teacher/lib/csvImport";
import { clearAllDrafts, draftKey, readDraft, writeDraft } from "@/features/teacher/lib/drafts";
import {
  validateLeaderChange,
  validateMove,
  validateNewTeam,
  type AdjustTeam,
} from "@/features/teacher/lib/teamAdjustment";

function preview(text: string, name = "ds.csv"): ImportPreview {
  const result = readImportFile(name, text.length, text);
  if (!result.ok) throw new Error(result.problem);
  return result.preview;
}

describe("CSV reading", () => {
  it("parses quotes, doubled quotes, CRLF and a BOM", () => {
    const records = parseCsv('﻿a,b\r\n"x, y","say ""hi"""\r\n', ",");
    expect(records).toEqual([
      ["a", "b"],
      ["x, y", 'say "hi"'],
    ]);
  });

  it("numbers rows by their line in the file, header being row 1, and skips blank lines", () => {
    const result = preview("email,student_id\na@x.vn,1\n\n,\nb@x.vn,2\n");
    expect(result.rows.map((row) => row.rowNumber)).toEqual([2, 5]);
  });

  it("accepts the documented columns, common aliases and a semicolon delimiter", () => {
    const result = preview("MSSV;Email;Họ;Tên\n20210001;a@x.vn;Nguyễn Văn;A\n");
    expect(result.delimiter).toBe(";");
    expect(result.rows[0]).toMatchObject({
      studentId: "20210001",
      email: "a@x.vn",
      lastName: "Nguyễn Văn",
      firstName: "A",
      issues: [],
    });
  });

  it("flags a malformed email as an error and counts it", () => {
    const result = preview("email\nnot-an-email\nok@x.vn\n");
    expect(result.rows[0].issues.map((issue) => issue.code)).toEqual(["invalid-email"]);
    expect(result.errorCount).toBe(1);
    expect(result.readyCount).toBe(1);
  });

  it("flags a row with neither email nor student code", () => {
    const result = preview("email,student_id,first_name\n,,An\n");
    expect(result.rows[0].issues.map((issue) => issue.code)).toEqual(["no-identity"]);
  });

  it("says a student-code-only row can only find an existing account, and an email-only row is fine", () => {
    const result = preview("email,student_id\n,111\nb@x.vn,\n");
    expect(result.rows[0].issues).toEqual([expect.objectContaining({ code: "student-id-only", level: "warning" })]);
    expect(result.rows[1].issues).toEqual([expect.objectContaining({ code: "email-only", level: "info" })]);
    expect(result.errorCount).toBe(0);
  });

  it("marks duplicates inside the file by email (any case) or by student code, pointing at the first row", () => {
    const result = preview("email,student_id\nA@x.vn,1\na@X.vn,2\nc@x.vn,1\n");
    expect(result.rows[0].issues).toEqual([]);
    expect(result.rows[1].issues[0]).toMatchObject({ code: "duplicate-in-file" });
    expect(result.rows[1].issues[0].message).toContain("dòng 2");
    expect(result.rows[2].issues[0].message).toContain("dòng 2");
    expect(result.duplicateCount).toBe(2);
  });

  it("refuses a spreadsheet with the reason, instead of guessing at binary content", () => {
    const result = readImportFile("ds.xlsx", 5000, "PK\u0003\u0004binary");
    expect(result).toEqual({ ok: false, problem: expect.stringContaining("chưa đọc được file Excel") });
    expect(isSpreadsheetFile("A.XLSX")).toBe(true);
    expect(isSpreadsheetFile("a.csv")).toBe(false);
  });

  it.each([
    ["ds.pdf", "email\na@x.vn", "Chỉ nhận file CSV"],
    ["ds.csv", "   \n", "File trống"],
    ["ds.csv", "ten,lop\nAn,1\n", "Thiếu cột định danh"],
    ["ds.csv", "email,student_id\n", "chỉ có dòng tiêu đề"],
  ])("refuses %s with a clear problem", (name, text, expected) => {
    const result = readImportFile(name, Math.max(text.length, 1), text);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.problem).toContain(expected);
  });

  it("refuses files over the interface limits and says the limit is not the backend's", () => {
    const big = readImportFile("ds.csv", MAX_IMPORT_BYTES + 1, "email\na@x.vn");
    const many = readImportFile(
      "ds.csv",
      100,
      `email\n${Array.from({ length: MAX_IMPORT_ROWS + 1 }, (_, i) => `u${i}@x.vn`).join("\n")}`,
    );
    for (const result of [big, many]) {
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.problem).toContain("chưa phải giới hạn của backend");
    }
  });
});

describe("Class form schema", () => {
  const valid = {
    ...emptyCourseForm,
    name: "Đồ án",
    term: "HK1 2026",
    startsOn: "2026-09-01",
    endsOn: "2026-12-31",
  };
  const messages = (values: object) => {
    const result = courseFormSchema.safeParse(values);
    return result.success ? [] : result.error.issues.map((issue) => `${issue.path.join(".")}: ${issue.message}`);
  };

  it("accepts a complete form and leaves the subject code optional", () => {
    expect(messages(valid)).toEqual([]);
  });

  it("requires an end date on or after the start date, reported on the end date", () => {
    expect(messages({ ...valid, endsOn: "2026-08-31" })).toEqual([
      "endsOn: Ngày kết thúc phải sau hoặc cùng ngày bắt đầu.",
    ]);
    expect(messages({ ...valid, endsOn: "2026-09-01" })).toEqual([]);
  });

  it("requires whole numbers from 1 and min not above max, without inventing an upper bound", () => {
    expect(messages({ ...valid, minMembers: "0" })[0]).toContain("minMembers");
    expect(messages({ ...valid, maxMembers: "2.5" })[0]).toContain("maxMembers");
    expect(messages({ ...valid, minMembers: "6", maxMembers: "5" })[0]).toContain("lớn hơn hoặc bằng");
    expect(messages({ ...valid, minMembers: "1", maxMembers: "500" })).toEqual([]);
  });

  it("rejects a short name and a subject code with unusual characters", () => {
    expect(messages({ ...valid, name: "ab" })[0]).toContain("name");
    expect(messages({ ...valid, courseCode: "SE 330!" })[0]).toContain("courseCode");
  });
});

const team = (teamId: string, size: number, leaders = 1, max = 5): AdjustTeam => ({
  teamId,
  name: `Team ${teamId}`,
  maxMembers: max,
  members: Array.from({ length: size }, (_, i) => ({
    userId: `${teamId}-u${i}`,
    name: `${teamId} thành viên ${i}`,
    role: i < leaders ? ("leader" as const) : ("member" as const),
  })),
});

describe("Team adjustment checks", () => {
  const base = { replacementLeaderId: null, minMembers: 3 };

  it("never allows a team to exceed its maximum size", () => {
    const verdict = validateMove({ ...base, studentId: "a-u2", fromTeam: team("a", 4), toTeam: team("b", 5) });
    expect(verdict.ok).toBe(false);
    expect(verdict.errors[0]).toContain("đủ sĩ số tối đa (5/5)");
    expect(verdict.errors[0]).toContain("Giao diện không cho vượt sĩ số");
  });

  it("does not let the only Leader leave without a replacement, and accepts a valid one", () => {
    const from = team("a", 4);
    const without = validateMove({ ...base, studentId: "a-u0", fromTeam: from, toTeam: team("b", 3) });
    expect(without.ok).toBe(false);
    expect(without.errors.join(" ")).toContain("sẽ mất Leader");

    const withOne = validateMove({ ...base, studentId: "a-u0", fromTeam: from, toTeam: team("b", 3), replacementLeaderId: "a-u1" });
    expect(withOne.ok).toBe(true);
    const outsider = validateMove({ ...base, studentId: "a-u0", fromTeam: from, toTeam: team("b", 3), replacementLeaderId: "zzz" });
    expect(outsider.ok).toBe(false);
  });

  it("lets a member, or one of two Leaders, leave without naming a replacement", () => {
    expect(validateMove({ ...base, studentId: "a-u2", fromTeam: team("a", 4), toTeam: team("b", 3) }).ok).toBe(true);
    expect(validateMove({ ...base, studentId: "a-u0", fromTeam: team("a", 4, 2), toTeam: team("b", 3) }).ok).toBe(true);
  });

  it("warns, but does not block, when the source falls below the minimum or empties, and always notes history", () => {
    const small = validateMove({ ...base, studentId: "a-u2", fromTeam: team("a", 3), toTeam: team("b", 3) });
    expect(small.ok).toBe(true);
    expect(small.warnings.join(" ")).toContain("ít hơn mức tối thiểu 3");
    expect(small.warnings.join(" ")).toContain("Lịch sử thành viên và đóng góp cũ được giữ nguyên");
    const empty = validateMove({ ...base, studentId: "a-u0", fromTeam: team("a", 1), toTeam: team("b", 3) });
    expect(empty.ok).toBe(true);
    expect(empty.warnings.join(" ")).toContain("không còn thành viên");
  });

  it("seats a student who has no team, and refuses a no-op or missing choices", () => {
    expect(validateMove({ ...base, studentId: "x", fromTeam: null, toTeam: team("b", 3) }).ok).toBe(true);
    expect(validateMove({ ...base, studentId: "a-u1", fromTeam: team("a", 3), toTeam: team("a", 3) }).errors).toContain(
      "Sinh viên đã ở nhóm này.",
    );
    expect(validateMove({ ...base, studentId: null, fromTeam: null, toTeam: null }).errors).toHaveLength(2);
  });

  it("designates a Leader only among the team's members", () => {
    const t = team("a", 3);
    expect(validateLeaderChange({ team: t, newLeaderId: "a-u1" }).ok).toBe(true);
    expect(validateLeaderChange({ team: t, newLeaderId: "a-u0" }).errors[0]).toContain("đã là Leader");
    expect(validateLeaderChange({ team: t, newLeaderId: "someone" }).errors[0]).toContain("số thành viên");
  });

  it("creates a team only with a unique name and a first Leader, and warns it starts below minimum", () => {
    const ok = validateNewTeam({ name: "Team Z", leaderId: "u1", existingNames: ["Team A"], minMembers: 3 });
    expect(ok.ok).toBe(true);
    expect(ok.warnings[0]).toContain("1 thành viên");
    expect(validateNewTeam({ name: "team a ", leaderId: "u1", existingNames: ["Team A"], minMembers: 3 }).errors).toContain(
      "Đã có nhóm trùng tên trong lớp.",
    );
    expect(validateNewTeam({ name: "ab", leaderId: null, existingNames: [], minMembers: 3 }).errors).toHaveLength(2);
  });
});

describe("Drafts", () => {
  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("keys a draft by user, so one account never sees another's", () => {
    const a = draftKey("user-a", "feedback", "team.x");
    const b = draftKey("user-b", "feedback", "team.x");
    expect(a).not.toBe(b);
    writeDraft(a, "nháp của A");
    expect(readDraft(a)).toBe("nháp của A");
    expect(readDraft(b)).toBe("");
  });

  it("removes the draft when it becomes empty", () => {
    const key = draftKey("u", "x");
    writeDraft(key, "abc");
    writeDraft(key, "");
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it("forgets drafts on sign-out and leaves unrelated storage alone", () => {
    writeDraft(draftKey("u", "a"), "x");
    writeDraft(draftKey("v", "b"), "y");
    sessionStorage.setItem("utask.mock.refresh-token", "keep");
    clearAllDrafts();
    expect(readDraft(draftKey("u", "a"))).toBe("");
    expect(readDraft(draftKey("v", "b"))).toBe("");
    expect(sessionStorage.getItem("utask.mock.refresh-token")).toBe("keep");
  });

  it("survives storage being unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readDraft("k")).toBe("");
    expect(() => writeDraft("k", "v")).not.toThrow();
  });
});
