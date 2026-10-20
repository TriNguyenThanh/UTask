import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { EpicDialog } from "@/features/projects/components/EpicDialog";
import { LabelManagerDialog } from "@/features/projects/components/LabelManagerDialog";
import { epicEditAccess } from "@/features/projects/lib/epicForm";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { Epic } from "@/features/projects/types";
import type { TaskScopeDto } from "@/lib/api/work/dto";
import { useEpicsReal, useScopedTasksReal, useTaskLifecycle } from "@/lib/query/workMetaHooks";
import { cn } from "@/lib/utils";

type Assignees = readonly { userId: string; name: string }[];

/** Nút "Tạo Epic" (Leader) của cột Epics ở Backlog. */
export function CreateEpicButton({ projectId, assignees }: Readonly<{ projectId: string; assignees: Assignees }>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="link" size="xs" className="h-auto p-0 text-xs" onClick={() => setOpen(true)}>
        <Plus className="size-3.5" aria-hidden />
        Tạo Epic
      </Button>
      <EpicDialog projectId={projectId} open={open} onOpenChange={setOpen} epic={null} access="all" assignees={assignees} />
    </>
  );
}

/**
 * Nút sửa một epic. Workspace chỉ giữ tên và màu, nên epic đầy đủ (lead, ngày, trạng thái) được tải khi mở.
 * Leader sửa mọi epic; người phụ trách epic sửa epic của mình với form giới hạn.
 */
export function EpicEditButton({
  projectId,
  epic,
  role,
  userId,
  assignees,
}: Readonly<{
  projectId: string;
  epic: Epic;
  role: "leader" | "member" | "none";
  userId: string;
  assignees: Assignees;
}>) {
  const [open, setOpen] = useState(false);
  const epics = useEpicsReal(projectId, open || role === "member");
  const dto = epics.data?.find((row) => row.id === epic.id) ?? null;
  const access = dto ? epicEditAccess(role, userId, dto) : role === "leader" ? "all" : null;
  if (!access) return null;
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        aria-label={`Sửa epic ${epic.name}`}
        className="shrink-0 text-muted-foreground"
        onClick={() => setOpen(true)}
      >
        <Pencil className="size-3" aria-hidden />
      </Button>
      {dto ? (
        <EpicDialog projectId={projectId} open={open} onOpenChange={setOpen} epic={dto} access={access} assignees={assignees} />
      ) : null}
    </>
  );
}

export function LabelManagerButton({ projectId }: Readonly<{ projectId: string }>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="link" size="xs" className="h-auto p-0 text-xs" onClick={() => setOpen(true)}>
        Quản lý nhãn
      </Button>
      <LabelManagerDialog projectId={projectId} open={open} onOpenChange={setOpen} />
    </>
  );
}

const SCOPES: readonly { value: TaskScopeDto; label: string }[] = [
  { value: "active", label: "Đang hoạt động" },
  { value: "archived", label: "Đã lưu trữ" },
  { value: "deleted", label: "Đã xóa" },
];

export function TaskScopeTabs({
  scope,
  onChange,
}: Readonly<{ scope: TaskScopeDto; onChange: (scope: TaskScopeDto) => void }>) {
  return (
    <div role="group" aria-label="Phạm vi issue" className="mb-4 flex gap-1.5">
      {SCOPES.map((option) => (
        <Button
          key={option.value}
          type="button"
          size="xs"
          variant={scope === option.value ? "default" : "outline"}
          aria-pressed={scope === option.value}
          className={cn("h-7")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

/** Issue đã lưu trữ hoặc đã xóa. Leader mở lại/khôi phục; người khác chỉ xem. */
export function ScopedTaskList({
  projectId,
  scope,
  canRestore,
}: Readonly<{ projectId: string; scope: Exclude<TaskScopeDto, "active">; canRestore: boolean }>) {
  const tasks = useScopedTasksReal(projectId, scope);
  const lifecycle = useTaskLifecycle();
  const action = scope === "archived" ? "unarchive" : "restore";

  if (tasks.isPending) return <p className="text-xs text-muted-foreground">Đang tải...</p>;
  if (tasks.error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        Không tải được danh sách issue.
      </p>
    );
  }
  if (tasks.data.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {scope === "archived" ? "Chưa có issue nào được lưu trữ." : "Chưa có issue nào bị xóa."}
      </p>
    );
  }
  return (
    <div>
      {lifecycle.error ? (
        <p className="mb-2 text-sm text-destructive" role="alert">
          {issueWriteErrorMessage(lifecycle.error)}
        </p>
      ) : null}
      <ul className="divide-y border-y">
        {tasks.data.map((task) => (
          <li key={task.id} className="flex items-center gap-3 px-3 py-2 text-sm">
            <span className="font-mono text-xs text-muted-foreground">{task.code}</span>
            <span className="min-w-0 flex-1 truncate">{task.title}</span>
            {canRestore ? (
              <Button
                type="button"
                size="xs"
                variant="outline"
                disabled={lifecycle.isPending}
                onClick={() =>
                  lifecycle.mutate(
                    { taskId: task.id, action, expectedVersion: task.version },
                    { onSuccess: () => toast.success(scope === "archived" ? "Đã mở lại issue." : "Đã khôi phục issue.") },
                  )
                }
              >
                {scope === "archived" ? "Mở lại" : "Khôi phục"}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
