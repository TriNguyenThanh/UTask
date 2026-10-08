/**
 * Client-side reading and format checks for a student list file.
 *
 * Scope on purpose: this only reads CSV and checks its SHAPE (columns, email
 * syntax, duplicates inside the file). It never decides who a person is: whether
 * an email already has an account, whether a student code belongs to someone
 * else, whether the person is a teacher or is already in the class — all of that
 * is the backend's call. Nothing here creates accounts, passwords or
 * enrollments, and nothing is sent.
 *
 * Column names follow the Identity spec §3.5.1 (`student_id`, `email`,
 * `first_name`, `last_name`); a few common aliases are accepted.
 */

export const MAX_IMPORT_BYTES = 1024 * 1024;
export const MAX_IMPORT_ROWS = 2000;

export type ImportIssueLevel = "error" | "warning" | "info";

export interface ImportIssue {
  code: "invalid-email" | "no-identity" | "duplicate-in-file" | "student-id-only" | "email-only";
  level: ImportIssueLevel;
  message: string;
}

export interface ImportRow {
  /** Line of the record in the file; the header is row 1 (matches the backend's `row_number`). */
  rowNumber: number;
  studentId: string;
  email: string;
  firstName: string;
  lastName: string;
  issues: ImportIssue[];
}

export interface ImportPreview {
  fileName: string;
  delimiter: "," | ";" | "\t";
  rows: ImportRow[];
  /** Which known columns the file has, by canonical name. */
  columns: string[];
  /** Rows with no error-level issue. */
  readyCount: number;
  errorCount: number;
  warningCount: number;
  duplicateCount: number;
}

export type ImportReadResult =
  | { ok: true; preview: ImportPreview }
  | { ok: false; problem: string };

const COLUMN_ALIASES: Record<string, "student_id" | "email" | "first_name" | "last_name"> = {
  student_id: "student_id",
  mssv: "student_id",
  ma_sinh_vien: "student_id",
  ma_so_sinh_vien: "student_id",
  email: "email",
  email_sinh_vien: "email",
  first_name: "first_name",
  ten: "first_name",
  last_name: "last_name",
  ho: "last_name",
  ho_dem: "last_name",
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function normalizeHeader(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/gi, "d")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function detectDelimiter(firstLine: string): "," | ";" | "\t" {
  const counts = {
    ",": firstLine.split(",").length,
    ";": firstLine.split(";").length,
    "\t": firstLine.split("\t").length,
  };
  return (Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0] as "," | ";" | "\t") ?? ",";
}

/** RFC 4180-style records: quoted fields, doubled quotes, CRLF or LF, optional BOM. */
export function parseCsv(text: string, delimiter: string): string[][] {
  const source = text.replace(/^﻿/, "");
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (inQuotes) {
      if (char === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      record.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && source[i + 1] === "\n") i += 1;
      record.push(field);
      records.push(record);
      record = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field !== "" || record.length > 0) {
    record.push(field);
    records.push(record);
  }
  return records;
}

export function isSpreadsheetFile(fileName: string): boolean {
  return /\.(xlsx|xls|xlsm)$/i.test(fileName);
}

/**
 * Checks that depend only on the file's name and size. Run BEFORE the content
 * is read, so a huge or binary file is refused without ever being loaded into
 * memory. Returns the reason to refuse, or null.
 */
export function preflightImportFile(fileName: string, size: number): string | null {
  if (isSpreadsheetFile(fileName)) {
    return "Ứng dụng chưa đọc được file Excel (.xlsx) vì chưa có thư viện đọc Excel. Hãy xuất sang CSV (UTF-8) rồi chọn lại.";
  }
  if (!/\.csv$/i.test(fileName) && !/\.txt$/i.test(fileName)) {
    return "Chỉ nhận file CSV (.csv). File Excel cần được xuất sang CSV trước.";
  }
  if (size === 0) {
    return "File trống: không có dòng nào để kiểm tra.";
  }
  if (size > MAX_IMPORT_BYTES) {
    return `File lớn hơn ${Math.round(MAX_IMPORT_BYTES / 1024)} KB, vượt giới hạn mà giao diện đặt để không bị treo (chưa phải giới hạn của backend). Hãy chia nhỏ file.`;
  }
  return null;
}

/**
 * Reads CSV text into a preview. Spreadsheet files are refused with a clear
 * reason: the app has no Excel reader, and guessing at binary content would
 * be worse than asking for a CSV export.
 */
export function readImportFile(fileName: string, size: number, text: string): ImportReadResult {
  const early = preflightImportFile(fileName, size);
  if (early) {
    return { ok: false, problem: early };
  }
  if (text.trim() === "") {
    return { ok: false, problem: "File trống: không có dòng nào để kiểm tra." };
  }

  const firstLine = text.replace(/^﻿/, "").split(/\r?\n/, 1)[0] ?? "";
  const delimiter = detectDelimiter(firstLine);
  const records = parseCsv(text, delimiter);
  const header = records[0] ?? [];
  const columnIndex: Partial<Record<"student_id" | "email" | "first_name" | "last_name", number>> = {};
  header.forEach((cell, index) => {
    const canonical = COLUMN_ALIASES[normalizeHeader(cell)];
    if (canonical && columnIndex[canonical] === undefined) columnIndex[canonical] = index;
  });
  if (columnIndex.email === undefined && columnIndex.student_id === undefined) {
    return {
      ok: false,
      problem:
        "Thiếu cột định danh: file cần ít nhất cột email hoặc student_id (mssv) ở dòng đầu tiên.",
    };
  }

  const dataRecords = records.slice(1);
  if (dataRecords.length > MAX_IMPORT_ROWS) {
    return {
      ok: false,
      problem: `File có ${dataRecords.length} dòng, vượt giới hạn ${MAX_IMPORT_ROWS} dòng mà giao diện đặt (chưa phải giới hạn của backend). Hãy chia nhỏ file.`,
    };
  }

  const cell = (record: string[], key: keyof typeof columnIndex) =>
    columnIndex[key] === undefined ? "" : (record[columnIndex[key] as number] ?? "").trim();

  const rows: ImportRow[] = [];
  const firstSeen = new Map<string, number>();
  dataRecords.forEach((record, index) => {
    if (record.every((value) => value.trim() === "")) return; // blank line: skipped, row number kept
    const rowNumber = index + 2;
    const studentId = cell(record, "student_id");
    const email = cell(record, "email");
    const issues: ImportIssue[] = [];

    if (!studentId && !email) {
      issues.push({
        code: "no-identity",
        level: "error",
        message: "Dòng không có email lẫn mã sinh viên nên không xác định được người cần thêm.",
      });
    } else {
      if (email && !EMAIL_PATTERN.test(email)) {
        issues.push({ code: "invalid-email", level: "error", message: "Email sai định dạng." });
      }
      if (studentId && !email) {
        issues.push({
          code: "student-id-only",
          level: "warning",
          message: "Chỉ có mã sinh viên: hệ thống chỉ tìm tài khoản có sẵn, không tạo tài khoản mới.",
        });
      }
      if (email && !studentId && EMAIL_PATTERN.test(email)) {
        issues.push({
          code: "email-only",
          level: "info",
          message: "Chưa có mã sinh viên; vẫn hợp lệ nếu chỉ có email.",
        });
      }
    }

    for (const key of [email ? `e:${email.toLowerCase()}` : "", studentId ? `s:${studentId.toLowerCase()}` : ""]) {
      if (!key) continue;
      const first = firstSeen.get(key);
      if (first === undefined) {
        firstSeen.set(key, rowNumber);
      } else if (!issues.some((issue) => issue.code === "duplicate-in-file")) {
        issues.push({
          code: "duplicate-in-file",
          level: "warning",
          message: `Trùng với dòng ${first} trong file. Hệ thống sẽ đánh dấu dòng trùng.`,
        });
      }
    }

    rows.push({
      rowNumber,
      studentId,
      email,
      firstName: cell(record, "first_name"),
      lastName: cell(record, "last_name"),
      issues,
    });
  });

  if (rows.length === 0) {
    return { ok: false, problem: "File chỉ có dòng tiêu đề, chưa có sinh viên nào." };
  }

  const hasLevel = (row: ImportRow, level: ImportIssueLevel) => row.issues.some((issue) => issue.level === level);
  return {
    ok: true,
    preview: {
      fileName,
      delimiter,
      rows,
      columns: (Object.keys(columnIndex) as string[]).sort(),
      readyCount: rows.filter((row) => !hasLevel(row, "error")).length,
      errorCount: rows.filter((row) => hasLevel(row, "error")).length,
      warningCount: rows.filter((row) => hasLevel(row, "warning")).length,
      duplicateCount: rows.filter((row) => row.issues.some((issue) => issue.code === "duplicate-in-file")).length,
    },
  };
}
