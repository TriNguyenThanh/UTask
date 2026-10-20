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
import {
  EMPTY_EPIC_FORM,
  EPIC_NAME_MAX,
  EPIC_STATUS_OPTIONS,
  formValuesOfEpic,
  toCreateEpicInput,
  toPatchEpicInput,
  validateEpicForm,
  type EpicFormErrors,
  type EpicFormValues,
} from "@/features/projects/lib/epicForm";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { EpicDto, EpicStatusDto } from "@/lib/api/work/dto";
import { useCreateEpic, useDeleteEpic, usePatchEpic } from "@/lib/query/workMetaHooks";

const SELECT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Tạo hoặc sửa epic. `epic === null` là tạo (Leader). `access = "limited"`: người phụ trách không phải
 * Leader chỉ sửa tên, mô tả, trạng thái nên các ô còn lại bị tắt. Xóa chỉ có cho Leader.
 */
export function EpicDialog({
  projectId,
  open,
  onOpenChange,
  epic,
  access,
  assignees,
}: Readonly<{
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  epic: EpicDto | null;
  access: "all" | "limited";
  assignees: readonly { userId: string; name: string }[];
}>) {
  const create = useCreateEpic(projectId);
  const patch = usePatchEpic(projectId, epic?.id ?? "");
  const remove = useDeleteEpic(projectId);
  const [values, setValues] = useState<EpicFormValues>(EMPTY_EPIC_FORM);
  const [errors, setErrors] = useState<EpicFormErrors>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { reset: resetCreate } = create;
  const { reset: resetPatch } = patch;

  useEffect(() => {
    if (!open) return;
    setValues(epic ? formValuesOfEpic(epic) : EMPTY_EPIC_FORM);
    setErrors({});
    setConfirmDelete(false);
    resetCreate();
    resetPatch();
  }, [open, epic, resetCreate, resetPatch]);

  const limited = access === "limited";
  const pending = create.isPending || patch.isPending;
  const serverError = create.error ?? patch.error ?? remove.error;

  function change(next: Partial<EpicFormValues>) {
    setValues((current) => ({ ...current, ...next }));
    setErrors({});
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validateEpicForm(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const done = (message: string) => ({
      onSuccess: () => {
        toast.success(message);
        onOpenChange(false);
      },
    });
    if (!epic) {
      create.mutate(toCreateEpicInput(values), done("Đã tạo epic."));
      return;
    }
    const input = toPatchEpicInput(formValuesOfEpic(epic), values, access);
    if (!input) {
      onOpenChange(false);
      return;
    }
    patch.mutate(input, done("Đã lưu epic."));
  }

  function confirmRemove() {
    if (!epic) return;
    remove.mutate(epic.id, {
      onSuccess: () => {
        toast.success("Đã xóa epic.");
        setConfirmDelete(false);
        onOpenChange(false);
      },
      onError: () => setConfirmDelete(false),
    });
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <form className="space-y-4" onSubmit={submit} aria-label={epic ? "Sửa epic" : "Tạo epic"}>
            <DialogHeader>
              <DialogTitle>{epic ? "Sửa epic" : "Tạo epic"}</DialogTitle>
              <DialogDescription>
                {limited ? "Bạn là người phụ trách epic này: chỉ sửa được tên, mô tả và trạng thái." : "Epic gom các issue cùng một mục tiêu lớn."}
              </DialogDescription>
            </DialogHeader>
            {serverError ? (
              <p className="text-sm text-destructive" role="alert">
                {issueWriteErrorMessage(serverError)}
              </p>
            ) : null}
            <fieldset className="min-w-0 space-y-4" disabled={pending || remove.isPending}>
              <div className="space-y-1.5">
                <Label htmlFor="epic-name">Tên epic</Label>
                <Input
                  id="epic-name"
                  value={values.name}
                  maxLength={EPIC_NAME_MAX}
                  autoComplete="off"
                  aria-invalid={errors.name ? true : undefined}
                  onChange={(event) => change({ name: event.target.value })}
                />
                <FieldError messages={errors.name ? [errors.name] : undefined} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="epic-description">Mô tả</Label>
                <Textarea
                  id="epic-description"
                  rows={3}
                  value={values.description}
                  onChange={(event) => change({ description: event.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="epic-status">Trạng thái</Label>
                <select
                  id="epic-status"
                  className={SELECT_CLASS}
                  value={values.status}
                  onChange={(event) => change({ status: event.target.value as EpicStatusDto })}
                >
                  {EPIC_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="epic-lead">Người phụ trách</Label>
                <select
                  id="epic-lead"
                  className={SELECT_CLASS}
                  value={values.leadUserId}
                  disabled={limited}
                  onChange={(event) => change({ leadUserId: event.target.value })}
                >
                  <option value="">Chưa có</option>
                  {assignees.map((member) => (
                    <option key={member.userId} value={member.userId}>
                      {member.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="epic-start">Ngày bắt đầu</Label>
                  <Input
                    id="epic-start"
                    type="date"
                    value={values.startDate}
                    disabled={limited}
                    onChange={(event) => change({ startDate: event.target.value })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="epic-target">Ngày mục tiêu</Label>
                  <Input
                    id="epic-target"
                    type="date"
                    value={values.targetDate}
                    disabled={limited}
                    aria-invalid={errors.targetDate ? true : undefined}
                    onChange={(event) => change({ targetDate: event.target.value })}
                  />
                  <FieldError messages={errors.targetDate ? [errors.targetDate] : undefined} />
                </div>
              </div>
            </fieldset>
            <DialogFooter>
              {epic && !limited ? (
                <Button type="button" variant="outline" className="mr-auto text-destructive" onClick={() => setConfirmDelete(true)} disabled={pending}>
                  Xóa epic
                </Button>
              ) : null}
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
                Hủy
              </Button>
              <Button type="submit" disabled={!values.name.trim() || pending}>
                {pending ? "Đang lưu..." : epic ? "Lưu" : "Tạo Epic"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={confirmDelete}
        title="Xóa epic?"
        description="Các issue thuộc epic này sẽ không còn thuộc epic nào."
        confirmLabel="Xóa epic"
        destructive
        pending={remove.isPending}
        onConfirm={confirmRemove}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
