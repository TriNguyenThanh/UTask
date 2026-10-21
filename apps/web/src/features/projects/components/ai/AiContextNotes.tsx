import type { AiContextDto, AiContextSourceDto } from "@/lib/api/ai/dto";

const DOMAIN: Record<AiContextSourceDto["domain"], string> = {
  project: "dự án",
  task: "nhiệm vụ",
  sprint: "sprint",
  progress: "tiến độ",
  github_activity: "GitHub",
  team: "nhóm",
};

const STATUS: Record<AiContextSourceDto["status"], string> = {
  available: "đầy đủ",
  stale: "đã cũ",
  missing: "thiếu",
  partial: "thiếu một phần",
  unavailable: "không tải được",
};

/** Cảnh báo của AI và nguồn ngữ cảnh không đầy đủ, để người dùng cân nhắc trước khi chấp nhận. */
export function contextNotes(warnings: readonly string[], context: AiContextDto | null): string[] {
  const sources = (context?.sources ?? [])
    .filter((source) => source.status !== "available")
    .map((source) => {
      const base = `Ngữ cảnh ${DOMAIN[source.domain]}: ${STATUS[source.status]}`;
      return source.warning ? `${base} — ${source.warning}` : base;
    });
  return [...warnings, ...sources];
}

export function AiContextNotes({ warnings, context }: Readonly<{ warnings: readonly string[]; context: AiContextDto | null }>) {
  const notes = contextNotes(warnings, context);
  if (notes.length === 0) return null;
  return (
    <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800" aria-label="Lưu ý từ AI">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}
