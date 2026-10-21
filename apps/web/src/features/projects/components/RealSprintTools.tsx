import { CheckCircle2, Pencil, Play, Plus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FieldError } from "@/features/notifications/components/FieldError";
import { burndownLines, toPolyline } from "@/features/projects/lib/burndown";
import { sprintWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import {
  EMPTY_SPRINT_FORM,
  SPRINT_NAME_MAX,
  toCreateSprintInput,
  toPatchSprintInput,
  validateSprintForm,
  type SprintFormErrors,
  type SprintFormValues,
} from "@/features/projects/lib/sprintForm";
import type { Issue, Sprint } from "@/features/projects/types";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import {
  useCloseSprint,
  useCreateSprint,
  usePatchSprint,
  useSprintBurndown,
  useSprintProgress,
  useStartSprint,
} from "@/lib/query/workSprintHooks";

/** Tạo (`sprint === null`) hoặc sửa tên, mục tiêu, ngày của một sprint chưa đóng. */
function SprintDialog({
  projectId,
  sprint,
  open,
  onOpenChange,
}: Readonly<{
  projectId: string;
  sprint: Sprint | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>) {
  const create = useCreateSprint(projectId);
  const patch = usePatchSprint(sprint?.id ?? "");
  const [values, setValues] = useState<SprintFormValues>(EMPTY_SPRINT_FORM);
  const [errors, setErrors] = useState<SprintFormErrors>({});
  const { reset: resetCreate } = create;
  const { reset: resetPatch } = patch;
  const initial: SprintFormValues | null = sprint
    ? { name: sprint.name, goal: sprint.goal, startDate: sprint.startDate, endDate: sprint.endDate }
    : null;

  useEffect(() => {
    if (!open) return;
    setValues(
      sprint
        ? { name: sprint.name, goal: sprint.goal, startDate: sprint.startDate, endDate: sprint.endDate }
        : EMPTY_SPRINT_FORM,
    );
    setErrors({});
    resetCreate();
    resetPatch();
  }, [open, sprint, resetCreate, resetPatch]);

  const pending = create.isPending || patch.isPending;
  const serverError = create.error ?? patch.error;

  function change(next: Partial<SprintFormValues>) {
    setValues((current) => ({ ...current, ...next }));
    setErrors({});
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateSprintForm(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const done = (message: string) => ({
      onSuccess: () => {
        toast.success(message);
        onOpenChange(false);
      },
    });
    if (!initial) {
      create.mutate(toCreateSprintInput(values), done("Đã tạo sprint."));
      return;
    }
    const input = toPatchSprintInput(initial, values);
    if (!input) {
      onOpenChange(false);
      return;
    }
    patch.mutate(input, done("Đã lưu sprint."));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form className="space-y-4" onSubmit={submit} aria-label={sprint ? "Sửa sprint" : "Tạo sprint"}>
          <DialogHeader>
            <DialogTitle>{sprint ? "Sửa sprint" : "Tạo sprint"}</DialogTitle>
            <DialogDescription>Sprint cần đủ ngày bắt đầu và ngày kết thúc mới bắt đầu được.</DialogDescription>
          </DialogHeader>
          {serverError ? (
            <p className="text-sm text-destructive" role="alert">
              {sprintWriteErrorMessage(serverError)}
            </p>
          ) : null}
          <fieldset className="min-w-0 space-y-4" disabled={pending}>
            <div className="space-y-1.5">
              <Label htmlFor="sprint-name">Tên sprint</Label>
              <Input
                id="sprint-name"
                value={values.name}
                maxLength={SPRINT_NAME_MAX}
                autoComplete="off"
                aria-invalid={errors.name ? true : undefined}
                onChange={(event) => change({ name: event.target.value })}
              />
              <FieldError messages={errors.name ? [errors.name] : undefined} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sprint-goal">Mục tiêu</Label>
              <Textarea
                id="sprint-goal"
                rows={2}
                value={values.goal}
                onChange={(event) => change({ goal: event.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="sprint-start">Ngày bắt đầu</Label>
                <Input
                  id="sprint-start"
                  type="date"
                  value={values.startDate}
                  onChange={(event) => change({ startDate: event.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sprint-end">Ngày kết thúc</Label>
                <Input
                  id="sprint-end"
                  type="date"
                  value={values.endDate}
                  aria-invalid={errors.endDate ? true : undefined}
                  onChange={(event) => change({ endDate: event.target.value })}
                />
                <FieldError messages={errors.endDate ? [errors.endDate] : undefined} />
              </div>
            </div>
          </fieldset>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Đang lưu…" : sprint ? "Lưu" : "Tạo sprint"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function CreateSprintButton({ projectId }: Readonly<{ projectId: string }>) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => setOpen(true)}>
        <Plus className="size-3.5" aria-hidden />
        Tạo Sprint
      </Button>
      <SprintDialog projectId={projectId} sprint={null} open={open} onOpenChange={setOpen} />
    </>
  );
}

const UNFINISHED_GROUPS = new Set(["COMPLETED", "CANCELLED"]);

/** Chọn nơi đặt issue chưa xong rồi đóng sprint đang chạy. `idempotencyKey` sinh mỗi lần mở hộp. */
function CloseSprintDialog({
  sprint,
  unfinished,
  targets,
  open,
  onOpenChange,
}: Readonly<{
  sprint: Sprint;
  unfinished: number;
  targets: readonly Sprint[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>) {
  const close = useCloseSprint(sprint.id);
  const [target, setTarget] = useState("");
  const [key, setKey] = useState(newIdempotencyKey);
  const { reset } = close;

  useEffect(() => {
    if (!open) return;
    setTarget("");
    setKey(newIdempotencyKey());
    reset();
  }, [open, reset]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    close.mutate(
      { targetSprintId: target === "" ? null : target, idempotencyKey: key },
      {
        onSuccess: () => {
          toast.success("Đã hoàn thành sprint.");
          onOpenChange(false);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form className="space-y-4" onSubmit={submit} aria-label="Hoàn thành sprint">
          <DialogHeader>
            <DialogTitle>Hoàn thành {sprint.name}</DialogTitle>
            <DialogDescription>
              {unfinished > 0
                ? `${unfinished} issue chưa xong. Chọn nơi chuyển chúng tới.`
                : "Mọi issue đã xong. Sprint sẽ được đóng và không thể mở lại."}
            </DialogDescription>
          </DialogHeader>
          {close.error ? (
            <p className="text-sm text-destructive" role="alert">
              {sprintWriteErrorMessage(close.error)}
            </p>
          ) : null}
          {unfinished > 0 ? (
            <div className="space-y-1.5">
              <Label htmlFor="close-target">Issue chưa xong</Label>
              <select
                id="close-target"
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={target}
                disabled={close.isPending}
                onChange={(event) => setTarget(event.target.value)}
              >
                <option value="">Trả về Product Backlog</option>
                {targets.map((other) => (
                  <option key={other.id} value={other.id}>
                    Chuyển sang {other.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={close.isPending} onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={close.isPending}>
              {close.isPending ? "Đang đóng…" : "Hoàn thành sprint"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Nút của Leader trên đầu mỗi sprint: sửa, bắt đầu (sprint nháp có đủ hai ngày), hoàn thành (sprint đang chạy).
 * `sprints` là mọi sprint của dự án để chọn sprint nhận issue chưa xong.
 */
export function SprintHeaderActions({
  projectId,
  sprint,
  sprints,
  issues,
}: Readonly<{
  projectId: string;
  sprint: Sprint;
  sprints: readonly Sprint[];
  issues: readonly Issue[];
}>) {
  const [editOpen, setEditOpen] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [startKey, setStartKey] = useState(newIdempotencyKey);
  const start = useStartSprint(projectId, sprint.id);
  const hasDates = sprint.startDate !== "" && sprint.endDate !== "";
  const unfinished = issues.filter((issue) => !UNFINISHED_GROUPS.has(issue.stateGroup)).length;

  function confirmStart() {
    start.mutate(
      { idempotencyKey: startKey },
      {
        onSuccess: () => {
          toast.success("Đã bắt đầu sprint.");
          setStartOpen(false);
        },
        onError: (error) => {
          setStartOpen(false);
          setStartKey(newIdempotencyKey());
          toast.error(sprintWriteErrorMessage(error));
        },
      },
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="text-xs"
        aria-label={`Sửa ${sprint.name}`}
        onClick={() => setEditOpen(true)}
      >
        <Pencil className="size-3.5" aria-hidden />
      </Button>
      {sprint.state === "upcoming" ? (
        <Button
          type="button"
          variant="outline"
          size="xs"
          className="text-xs"
          disabled={!hasDates}
          title={hasDates ? undefined : "Cần đặt ngày bắt đầu và ngày kết thúc trước"}
          onClick={() => setStartOpen(true)}
        >
          <Play className="size-3.5" aria-hidden />
          Bắt đầu Sprint
        </Button>
      ) : null}
      {sprint.state === "active" ? (
        <Button type="button" variant="outline" size="xs" className="text-xs" onClick={() => setCloseOpen(true)}>
          <CheckCircle2 className="size-3.5" aria-hidden />
          Hoàn thành Sprint
        </Button>
      ) : null}
      <SprintDialog projectId={projectId} sprint={sprint} open={editOpen} onOpenChange={setEditOpen} />
      <ConfirmDialog
        open={startOpen}
        title={`Bắt đầu ${sprint.name}?`}
        description="Mỗi dự án chỉ có một sprint đang chạy. Sau khi bắt đầu, thêm hoặc bớt issue phải kèm lý do."
        confirmLabel="Bắt đầu"
        pending={start.isPending}
        onConfirm={confirmStart}
        onCancel={() => setStartOpen(false)}
      />
      <CloseSprintDialog
        sprint={sprint}
        unfinished={unfinished}
        targets={sprints.filter((other) => other.state === "upcoming")}
        open={closeOpen}
        onOpenChange={setCloseOpen}
      />
    </div>
  );
}

function Stat({ label, value }: Readonly<{ label: string; value: string | number }>) {
  return (
    <div className="flex flex-col">
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm font-semibold">{value}</dd>
    </div>
  );
}

const CHART_W = 240;
const CHART_H = 70;

/** Số liệu tiến độ và burndown theo điểm ước lượng của sprint đang chạy (công thức do Work tính). */
export function SprintInsights({ sprintId }: Readonly<{ sprintId: string }>) {
  const progress = useSprintProgress(sprintId);
  const burndown = useSprintBurndown(sprintId);
  const totals = progress.data?.totals;
  const lines = burndown.data ? burndownLines(burndown.data.days, CHART_W, CHART_H) : null;

  if (progress.isError && burndown.isError) {
    return <p className="px-3 py-2 text-xs text-destructive">Không tải được số liệu sprint.</p>;
  }

  return (
    <div className="mb-3 flex flex-wrap items-start gap-6 rounded-md border bg-muted/20 px-3 py-2" aria-label="Tiến độ sprint">
      {totals ? (
        <dl className="flex flex-wrap gap-x-5 gap-y-2">
          <Stat
            label="Hoàn thành"
            value={totals.completion_percent === null ? "—" : `${Math.round(totals.completion_percent)}%`}
          />
          <Stat label="Việc xong" value={`${totals.completed_work_item_count}/${totals.work_item_count}`} />
          <Stat label="Điểm xong" value={`${totals.completed_estimate_points}/${totals.known_estimate_points}`} />
          <Stat label="Bị chặn" value={totals.blocked_task_count} />
          <Stat label="Quá hạn" value={totals.overdue_task_count} />
          <Stat label="Chưa ước lượng" value={totals.unestimated_count} />
        </dl>
      ) : (
        <p className="text-xs text-muted-foreground">Đang tải tiến độ…</p>
      )}
      {lines ? (
        <figure className="m-0">
          <svg
            role="img"
            aria-label="Burndown: điểm còn lại theo ngày"
            viewBox={`-4 -4 ${CHART_W + 8} ${CHART_H + 8}`}
            width={CHART_W}
            height={CHART_H}
            className="overflow-visible"
          >
            <polyline points={toPolyline(lines.ideal)} fill="none" stroke="currentColor" strokeOpacity={0.3} strokeDasharray="4 3" />
            <polyline points={toPolyline(lines.remaining)} fill="none" stroke="var(--primary, currentColor)" strokeWidth={2} />
          </svg>
          <figcaption className="text-[10px] text-muted-foreground">
            Điểm còn lại theo ngày (tối đa {lines.max})
            {burndown.data?.window_truncated ? " · chỉ hiện giai đoạn gần nhất" : ""}
          </figcaption>
        </figure>
      ) : null}
    </div>
  );
}
