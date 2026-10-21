import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { Issue } from "@/features/projects/types";
import type { RelationTypeDto, TaskDto } from "@/lib/api/work/dto";
import {
  useCreateRelation,
  useDeleteRelation,
  useLabelsReal,
  useSetTaskLabels,
  useTaskLifecycle,
} from "@/lib/query/workMetaHooks";

const SELECT_CLASS =
  "h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export const RELATION_LABELS: Record<RelationTypeDto, string> = {
  BLOCKS: "Chặn",
  BLOCKED_BY: "Bị chặn bởi",
  DUPLICATE: "Trùng với",
  RELATES_TO: "Liên quan tới",
};

function ErrorLine({ error }: Readonly<{ error: unknown }>) {
  if (!error) return null;
  return (
    <p className="text-xs text-destructive" role="alert">
      {issueWriteErrorMessage(error)}
    </p>
  );
}

/** Gán/bỏ nhãn: mỗi lần tích gửi một lệnh ADD/REMOVE kèm `version` hiện tại của task. */
export function TaskLabelsEditor({ projectId, task }: Readonly<{ projectId: string; task: TaskDto }>) {
  const labels = useLabelsReal(projectId);
  const setLabels = useSetTaskLabels(task.id);
  if (!labels.data || labels.data.length === 0) {
    return labels.data ? <p className="text-xs text-muted-foreground">Dự án chưa có nhãn nào.</p> : null;
  }
  return (
    <fieldset className="space-y-1.5" disabled={setLabels.isPending}>
      <legend className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Nhãn</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {labels.data.map((label) => {
          const checked = task.label_ids.includes(label.id);
          return (
            <label key={label.id} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={checked}
                onChange={() =>
                  setLabels.mutate({
                    expectedVersion: task.version,
                    action: checked ? "REMOVE" : "ADD",
                    labelIds: [label.id],
                  })
                }
              />
              <span className="size-2.5 rounded-full" style={{ backgroundColor: label.color }} aria-hidden />
              {label.name}
            </label>
          );
        })}
      </div>
      <ErrorLine error={setLabels.error} />
    </fieldset>
  );
}

/** Liên kết task: hiển thị theo góc nhìn của task đang xem; thêm/xóa cần quyền sửa task. */
export function TaskRelationsEditor({
  task,
  candidates,
}: Readonly<{ task: TaskDto; candidates: readonly Pick<Issue, "id" | "key" | "title">[] }>) {
  const create = useCreateRelation(task.id);
  const remove = useDeleteRelation(task.id);
  const [type, setType] = useState<RelationTypeDto>("BLOCKS");
  const [target, setTarget] = useState("");
  const pending = create.isPending || remove.isPending;
  const options = candidates.filter((issue) => issue.id !== task.id);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!target) return;
    create.mutate({ relatedTaskId: target, relationType: type }, { onSuccess: () => setTarget("") });
  }

  return (
    <section className="space-y-2" aria-label="Liên kết issue">
      <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Liên kết</h4>
      {task.relations && task.relations.length > 0 ? (
        <ul className="space-y-1">
          {task.relations.map((relation) => (
            <li key={relation.id} className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">{RELATION_LABELS[relation.relation_type]}</span>
              <span className="font-mono text-xs">{relation.related_task_code}</span>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                className="ml-auto text-destructive"
                disabled={pending}
                aria-label={`Gỡ liên kết với ${relation.related_task_code}`}
                onClick={() => remove.mutate(relation.id)}
              >
                Gỡ
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Chưa có liên kết nào.</p>
      )}
      <form className="flex gap-2" onSubmit={submit} aria-label="Thêm liên kết">
        <select
          className={SELECT_CLASS}
          value={type}
          aria-label="Loại liên kết"
          disabled={pending}
          onChange={(event) => setType(event.target.value as RelationTypeDto)}
        >
          {(Object.keys(RELATION_LABELS) as RelationTypeDto[]).map((value) => (
            <option key={value} value={value}>
              {RELATION_LABELS[value]}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          value={target}
          aria-label="Issue đích"
          disabled={pending}
          onChange={(event) => setTarget(event.target.value)}
        >
          <option value="">Chọn issue...</option>
          {options.map((issue) => (
            <option key={issue.id} value={issue.id}>
              {issue.key} — {issue.title}
            </option>
          ))}
        </select>
        <Button type="submit" size="sm" disabled={!target || pending}>
          Thêm
        </Button>
      </form>
      <ErrorLine error={create.error ?? remove.error} />
    </section>
  );
}

/** Lưu trữ hoặc xóa mềm issue (Leader). Xóa cascade cả nhiệm vụ con nên cần xác nhận. */
export function TaskLifecycleActions({ task, onGone }: Readonly<{ task: TaskDto; onGone: () => void }>) {
  const lifecycle = useTaskLifecycle();
  const [asking, setAsking] = useState<"archive" | "delete" | null>(null);

  function confirm() {
    if (!asking) return;
    lifecycle.mutate(
      { taskId: task.id, action: asking, expectedVersion: task.version },
      {
        onSuccess: () => {
          toast.success(asking === "archive" ? "Đã lưu trữ issue." : "Đã xóa issue.");
          onGone();
        },
        onSettled: () => setAsking(null),
      },
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setAsking("archive")}>
          Lưu trữ
        </Button>
        <Button type="button" variant="outline" size="sm" className="text-destructive" onClick={() => setAsking("delete")}>
          Xóa
        </Button>
      </div>
      <ErrorLine error={lifecycle.error} />
      <ConfirmDialog
        open={asking !== null}
        title={asking === "archive" ? "Lưu trữ issue?" : "Xóa issue?"}
        description={
          asking === "archive"
            ? "Issue được ẩn khỏi Board và Backlog; mở lại từ mục Đã lưu trữ ở Backlog."
            : "Issue và các nhiệm vụ con bị xóa; khôi phục từ mục Đã xóa ở Backlog."
        }
        confirmLabel={asking === "archive" ? "Lưu trữ" : "Xóa issue"}
        destructive={asking === "delete"}
        pending={lifecycle.isPending}
        onConfirm={confirm}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
