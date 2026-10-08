import { AlertTriangle, CheckCircle2, FileSpreadsheet, Info } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DisabledAction } from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import {
  MAX_IMPORT_ROWS,
  preflightImportFile,
  readImportFile,
  type ImportIssue,
  type ImportPreview,
  type ImportRow,
} from "@/features/teacher/lib/csvImport";
import { cn } from "@/lib/utils";

export const IMPORT_UNAVAILABLE =
  "Xác nhận nhập chưa khả dụng: chưa có hợp đồng API nhập danh sách của Classroom và ứng dụng chưa gửi được file (multipart). File của bạn chưa được gửi đi, chưa có tài khoản hay enrollment nào được tạo.";

/** What the backend is described to report per row; shown as a legend, never as a result. */
const RESULT_LEGEND: { title: string; description: string }[] = [
  {
    title: "Tạo tài khoản mới, chờ kích hoạt",
    description: "Chưa có tài khoản: tạo mới, sinh viên kích hoạt qua email. Không ai đặt hộ mật khẩu.",
  },
  {
    title: "Dùng tài khoản có sẵn",
    description: "Email hoặc MSSV khớp một tài khoản sinh viên đã có; thêm vào lớp, không tạo mới.",
  },
  { title: "Đã thuộc lớp", description: "Sinh viên đã ở trong lớp này; không thêm lần nữa." },
  {
    title: "Cần kiểm tra",
    description:
      "Email thuộc giảng viên hoặc quản trị viên, hoặc tài khoản bị khóa/xóa: không thêm làm sinh viên.",
  },
  { title: "Xung đột danh tính", description: "MSSV và email trỏ về hai người khác nhau; không tự sửa." },
  { title: "Lỗi từng dòng", description: "Dòng lỗi hiện kèm lý do; các dòng khác vẫn được xử lý." },
];

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Không đọc được file."));
    reader.readAsText(file, "utf-8");
  });
}

const LEVEL_STYLE: Record<ImportIssue["level"], string> = {
  error: "bg-red-50 text-red-900",
  warning: "bg-amber-50 text-amber-950",
  info: "bg-slate-50 text-slate-700",
};

function RowIssues({ row }: { row: ImportRow }) {
  if (row.issues.length === 0) {
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <CheckCircle2 className="size-3.5 text-emerald-600" aria-hidden /> Đúng định dạng
      </span>
    );
  }
  return (
    <ul className="space-y-1">
      {row.issues.map((issue) => (
        <li key={issue.code} className={cn("flex items-start gap-1.5 rounded px-2 py-1 text-xs", LEVEL_STYLE[issue.level])}>
          {issue.level === "info" ? (
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          ) : (
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          )}
          <span>
            <span className="font-semibold">
              {issue.level === "error" ? "Lỗi: " : issue.level === "warning" ? "Lưu ý: " : "Ghi chú: "}
            </span>
            {issue.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

function fullName(row: ImportRow): string {
  return [row.lastName, row.firstName].filter(Boolean).join(" ") || "—";
}

function Preview({ preview, onlyProblems }: { preview: ImportPreview; onlyProblems: boolean }) {
  const rows = onlyProblems
    ? preview.rows.filter((row) => row.issues.some((issue) => issue.level !== "info"))
    : preview.rows;
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Không có dòng nào cần chú ý.</p>;
  }
  return (
    <>
      <div className="hidden overflow-x-auto rounded-lg border bg-card md:block">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Xem trước các dòng trong file {preview.fileName}</caption>
          <thead className="border-b bg-muted text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th scope="col" className="px-4 py-3 font-semibold">Dòng</th>
              <th scope="col" className="px-4 py-3 font-semibold">MSSV</th>
              <th scope="col" className="px-4 py-3 font-semibold">Email</th>
              <th scope="col" className="px-4 py-3 font-semibold">Họ và tên</th>
              <th scope="col" className="px-4 py-3 font-semibold">Kiểm tra định dạng</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((row) => (
              <tr key={row.rowNumber} className="align-top">
                <td className="px-4 py-3 font-mono text-xs">{row.rowNumber}</td>
                <td className="px-4 py-3 font-mono text-xs">{row.studentId || "—"}</td>
                <td className="px-4 py-3">{row.email || "—"}</td>
                <td className="px-4 py-3">{fullName(row)}</td>
                <td className="min-w-64 px-4 py-3"><RowIssues row={row} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {rows.map((row) => (
          <li key={row.rowNumber} className="space-y-2 rounded-lg border bg-card p-4 text-sm">
            <p className="font-medium">
              <span className="font-mono text-xs text-muted-foreground">Dòng {row.rowNumber}</span>{" "}
              {fullName(row)}
            </p>
            <p className="text-xs text-muted-foreground">
              {row.studentId || "—"} • {row.email || "—"}
            </p>
            <RowIssues row={row} />
          </li>
        ))}
      </ul>
    </>
  );
}

/**
 * T06. Three steps: choose a file → format check and preview (all in the
 * browser) → result. The result step cannot exist yet: there is no contract
 * to send the file to, so it shows what each row WILL be reported as once
 * there is one, and never an outcome.
 */
export function Component() {
  const course = useTeacherCourseContext();
  const inputId = useId();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [onlyProblems, setOnlyProblems] = useState(false);

  async function chooseFile(file: File | undefined) {
    setPreview(null);
    setProblem(null);
    setOnlyProblems(false);
    if (!file) return;
    // Refuse by name and size first: a huge or binary file is never read.
    const early = preflightImportFile(file.name, file.size);
    if (early) {
      setProblem(early);
      return;
    }
    setReading(true);
    try {
      const text = await readFileAsText(file);
      const result = readImportFile(file.name, file.size, text);
      if (result.ok) setPreview(result.preview);
      else setProblem(result.problem);
    } catch {
      setProblem("Không đọc được file. Hãy thử chọn lại.");
    } finally {
      setReading(false);
    }
  }

  const step = preview ? 2 : 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Nhập danh sách sinh viên</h2>
          <p className="text-sm text-muted-foreground">Lớp: {course.name}</p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/teacher/courses/${course.courseId}/students`}>Về danh sách sinh viên</Link>
        </Button>
      </div>

      <ol aria-label="Các bước" className="flex flex-wrap gap-2 text-sm">
        {["Chọn file", "Kiểm tra định dạng", "Kết quả"].map((label, index) => (
          <li
            key={label}
            aria-current={index + 1 === step ? "step" : undefined}
            className={cn(
              "rounded-full border px-3 py-1",
              index + 1 === step ? "border-primary bg-accent font-semibold text-accent-foreground" : "text-muted-foreground",
            )}
          >
            {index + 1}. {label}
          </li>
        ))}
      </ol>

      <Alert className="border-amber-300 bg-amber-50 text-amber-950">
        <AlertTitle>Chỉ kiểm tra định dạng, chưa nhập được</AlertTitle>
        <AlertDescription>{IMPORT_UNAVAILABLE}</AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileSpreadsheet className="size-4" aria-hidden /> 1. Chọn file CSV
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex max-w-lg flex-col gap-1">
            <label htmlFor={inputId} className="text-sm font-medium">
              File danh sách (.csv, UTF-8)
            </label>
            <Input
              id={inputId}
              type="file"
              accept=".csv,text/csv,.xlsx"
              onChange={(event) => {
                void chooseFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Dòng đầu là tiêu đề. Cần ít nhất cột <code>email</code> hoặc <code>student_id</code> (mssv); cột{" "}
            <code>last_name</code> (họ và tên đệm) và <code>first_name</code> (tên) là tùy chọn. Tối đa{" "}
            {MAX_IMPORT_ROWS} dòng mỗi file theo giới hạn của giao diện. Giao diện không tạo mật khẩu, không
            gửi thư kích hoạt và không đưa ai vào nhóm.
          </p>
          <p role="status" aria-live="polite" className="text-sm">
            {reading ? "Đang đọc file…" : ""}
          </p>
          {problem ? (
            <Alert variant="destructive">
              <AlertTitle>Không dùng được file này</AlertTitle>
              <AlertDescription>{problem}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {preview ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">2. Kiểm tra định dạng: {preview.fileName}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl aria-label="Tóm tắt kiểm tra" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-md border bg-background p-3">
                <dt className="text-xs text-muted-foreground">Tổng số dòng</dt>
                <dd className="text-2xl font-bold">{preview.rows.length}</dd>
              </div>
              <div className="rounded-md border bg-background p-3">
                <dt className="text-xs text-muted-foreground">Đúng định dạng</dt>
                <dd className="text-2xl font-bold">{preview.readyCount}</dd>
              </div>
              <div className="rounded-md border bg-background p-3">
                <dt className="text-xs text-muted-foreground">Dòng lỗi</dt>
                <dd className="text-2xl font-bold text-red-700">{preview.errorCount}</dd>
              </div>
              <div className="rounded-md border bg-background p-3">
                <dt className="text-xs text-muted-foreground">Dòng trùng trong file</dt>
                <dd className="text-2xl font-bold text-amber-700">{preview.duplicateCount}</dd>
              </div>
            </dl>
            <p className="text-xs text-muted-foreground">
              "Đúng định dạng" chưa có nghĩa là thêm được: hệ thống còn kiểm tra tài khoản, vai trò và việc đã
              thuộc lớp.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={onlyProblems}
                onChange={(event) => setOnlyProblems(event.target.checked)}
              />
              Chỉ hiện dòng có lỗi hoặc lưu ý
            </label>
            <Preview preview={preview} onlyProblems={onlyProblems} />
            <div className="flex flex-wrap items-center gap-2 border-t pt-4">
              <DisabledAction reason={IMPORT_UNAVAILABLE} variant="default">
                Xác nhận nhập
              </DisabledAction>
              <Button type="button" variant="ghost" onClick={() => void chooseFile(undefined)}>
                Chọn file khác
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">3. Kết quả</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground" role="status">
            Chưa có kết quả nào: file chưa được gửi. Khi có hợp đồng, báo cáo sẽ liệt kê từng dòng theo các nhóm
            dưới đây; sinh viên chỉ được tính là đã thêm khi dòng đó báo đã thuộc lớp.
          </p>
          <ul aria-label="Các loại kết quả theo dòng" className="grid gap-2 sm:grid-cols-2">
            {RESULT_LEGEND.map((item) => (
              <li key={item.title} className="rounded-md border bg-background p-3 text-sm">
                <Badge variant="outline">{item.title}</Badge>
                <p className="mt-1 text-xs text-muted-foreground">{item.description}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
