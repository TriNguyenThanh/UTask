import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { IssueEditForm } from "@/features/projects/components/IssueEditForm";
import { TaskLabelsEditor, TaskLifecycleActions, TaskRelationsEditor } from "@/features/projects/components/IssueExtras";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { Epic, Issue } from "@/features/projects/types";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useTaskReal } from "@/lib/query/workHooks";
import { useCreateSubtask } from "@/lib/query/workWriteHooks";

/** Khối "Chỉnh sửa" trong panel: nạp task thật để có `version` và giá trị gốc của từng ô. */
export function RealIssueEditor({
  projectId,
  issueId,
  epics,
  assignees,
  issues,
  textOnly,
  isLeader,
  onGone,
  onDirtyChange,
}: Readonly<{
  projectId: string;
  issueId: string;
  epics: readonly Epic[];
  assignees: readonly { userId: string; name: string }[];
  /** Issue của dự án, làm đích cho liên kết. */
  issues: readonly Pick<Issue, "id" | "key" | "title">[];
  textOnly: boolean;
  /** Chỉ Leader được lưu trữ/xóa. */
  isLeader: boolean;
  /** Gọi sau khi issue bị lưu trữ hoặc xóa (đóng panel). */
  onGone: () => void;
  /** Báo khối sửa có thay đổi chưa lưu. */
  onDirtyChange?: (dirty: boolean) => void;
}>) {
  const query = useTaskReal(issueId);
  if (!query.data) return null;
  return (
    <details className="rounded-lg border border-outline-subtle p-3">
      <summary className="cursor-pointer text-xs font-bold uppercase tracking-wider">Chỉnh sửa issue</summary>
      <div className="pt-3">
        <IssueEditForm task={query.data} epics={epics} assignees={assignees} textOnly={textOnly} onDirtyChange={onDirtyChange} />
        <div className="mt-4 space-y-4 border-t border-outline-subtle pt-4">
          <TaskLabelsEditor projectId={projectId} task={query.data} />
          <TaskRelationsEditor task={query.data} candidates={issues} />
        </div>
        {isLeader ? (
          <div className="mt-4 border-t border-outline-subtle pt-4">
            <TaskLifecycleActions task={query.data} onGone={onGone} />
          </div>
        ) : null}
      </div>
    </details>
  );
}

/** Thêm nhiệm vụ con. Khóa idempotency giữ nguyên khi gửi lại cùng tiêu đề, đổi khi tiêu đề đổi sau lỗi. */
export function SubtaskCreateForm({ parentId }: Readonly<{ parentId: string }>) {
  const create = useCreateSubtask(parentId);
  const [title, setTitle] = useState("");
  const [key, setKey] = useState(newIdempotencyKey);
  const [failed, setFailed] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    create.mutate(
      { title: trimmed, idempotencyKey: key },
      {
        onSuccess: () => {
          setTitle("");
          setKey(newIdempotencyKey());
          setFailed(false);
        },
        onError: (error) => {
          setFailed(true);
          toast.error(issueWriteErrorMessage(error));
        },
      },
    );
  }

  return (
    <form className="flex gap-2" onSubmit={submit} aria-label="Thêm nhiệm vụ con">
      <Input
        value={title}
        maxLength={300}
        placeholder="Thêm nhiệm vụ con..."
        aria-label="Tiêu đề nhiệm vụ con"
        disabled={create.isPending}
        onChange={(event) => {
          setTitle(event.target.value);
          if (failed) {
            setKey(newIdempotencyKey());
            setFailed(false);
          }
        }}
      />
      <Button type="submit" size="sm" disabled={!title.trim() || create.isPending}>
        Thêm
      </Button>
    </form>
  );
}
