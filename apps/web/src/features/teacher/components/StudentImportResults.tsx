import { useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { describeResult, mergeSummaries, type OutcomeTone } from "@/features/teacher/lib/importRun";
import type { ImportRowResultDto } from "@/lib/api/classroom/dto";
import type { ImportRun } from "@/lib/query/teacherClassHooks";
import { cn } from "@/lib/utils";

const TONE_STYLE: Record<OutcomeTone, string> = {
  success: "text-emerald-800",
  neutral: "text-slate-700",
  problem: "text-red-800",
};

const SUMMARY_LABELS = [
  ["total_records", "Tổng số dòng đã xử lý"],
  ["enrolled", "Đã thêm vào lớp"],
  ["already_enrolled", "Đã thuộc lớp"],
  ["failed", "Không thêm được"],
  ["created_accounts", "Tài khoản mới"],
  ["existing_accounts", "Tài khoản có sẵn"],
  ["flagged", "Cần kiểm tra"],
  ["duplicates", "Dòng trùng"],
] as const;

function ResultRow({ result }: Readonly<{ result: ImportRowResultDto }>) {
  const outcome = describeResult(result);
  return (
    <li className="space-y-0.5 rounded-md border bg-background p-3 text-sm">
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-xs text-muted-foreground">Dòng {result.row_number ?? "?"}</span>
        <span>{result.email || "—"}</span>
        <span className="font-mono text-xs">{result.student_id || ""}</span>
      </p>
      <p className={cn("text-xs font-semibold", TONE_STYLE[outcome.tone])}>{outcome.label}</p>
      {outcome.detail ? <p className="text-xs text-muted-foreground">{outcome.detail}</p> : null}
    </li>
  );
}

/**
 * Outcome of a real import: progress by batch, the server's summary and one
 * line per row. A failed batch stops the run; "Thử lại" resumes from it with
 * the same keys, so batches that already succeeded are never sent again.
 */
export function StudentImportResults({
  run,
  onRetry,
}: Readonly<{ run: ImportRun; onRetry: () => void }>) {
  const [onlyProblems, setOnlyProblems] = useState(false);
  const rows = run.results.flatMap((batch) => batch.results);
  const visible = onlyProblems ? rows.filter((row) => row.enrollment_result === "FAILED") : rows;
  const summary = mergeSummaries(run.results);

  return (
    <div className="space-y-4">
      <output className="block text-sm" aria-live="polite">
        {run.phase === "running" ? `Đang gửi lô ${run.doneBatches + 1}/${run.totalBatches}…` : null}
        {run.phase === "done" ? `Đã xử lý xong ${run.totalBatches} lô.` : null}
        {run.phase === "failed" ? `Đã xong ${run.doneBatches}/${run.totalBatches} lô, dừng ở lô ${run.doneBatches + 1}.` : null}
      </output>

      {run.phase === "failed" ? (
        <Alert variant="destructive">
          <AlertTitle>Một lô chưa gửi được</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              {classErrorMessage(run.error)} Các lô đã xong được giữ nguyên; bấm thử lại chỉ gửi từ lô lỗi, không
              ghi danh trùng.
            </p>
            <Button type="button" size="sm" variant="outline" onClick={onRetry}>
              Thử lại từ lô {run.doneBatches + 1}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {run.results.length > 0 ? (
        <>
          <dl aria-label="Tóm tắt kết quả" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SUMMARY_LABELS.map(([key, label]) => (
              <div key={key} className="rounded-md border bg-background p-3">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className={cn("text-2xl font-bold", key === "failed" && summary.failed > 0 && "text-red-700")}>
                  {summary[key]}
                </dd>
              </div>
            ))}
          </dl>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyProblems} onChange={(event) => setOnlyProblems(event.target.checked)} />
            <span>Chỉ hiện dòng không thêm được</span>
          </label>
          {visible.length === 0 ? (
            <p className="text-sm text-muted-foreground">Không có dòng nào cần chú ý.</p>
          ) : (
            <ul aria-label="Kết quả theo dòng" className="space-y-2">
              {visible.map((result) => (
                <ResultRow key={`${result.row_number}-${result.email ?? result.student_id}`} result={result} />
              ))}
            </ul>
          )}
        </>
      ) : null}
    </div>
  );
}
