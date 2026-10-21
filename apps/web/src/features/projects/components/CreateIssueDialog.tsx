import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { IssueFormFields } from "@/features/projects/components/IssueFormFields";
import {
  EMPTY_ISSUE_FORM,
  toCreateInput,
  validateIssueForm,
  type IssueFormErrors,
  type IssueFormValues,
} from "@/features/projects/lib/issueForm";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { Epic } from "@/features/projects/types";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useAddTaskToSprint, useCreateTask } from "@/lib/query/workWriteHooks";

const SHOWN_ON_FIELD = ["title", "story_points"];
const REASON_MAX = 4000;

function serverErrors(error: unknown): { fields: IssueFormErrors; form?: string } {
  if (!(error instanceof ApiError)) return { fields: {}, form: issueWriteErrorMessage(error) };
  if (error.code === "CONCURRENT_MUTATION_IN_PROGRESS" || error.code === "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD") {
    return { fields: {}, form: "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại." };
  }
  if (error.code === "VALIDATION_ERROR") {
    const keys = Object.keys(error.fieldErrors);
    const fields: IssueFormErrors = {};
    if (error.fieldErrors.title) fields.title = error.fieldErrors.title.join(" ");
    if (error.fieldErrors.story_points) fields.storyPoints = error.fieldErrors.story_points.join(" ");
    // Lỗi của ô không có chỗ hiển thị phải hiện ở đầu form, không được mất.
    const allShown = keys.length > 0 && keys.every((key) => SHOWN_ON_FIELD.includes(key));
    return { fields, form: allShown ? undefined : error.message };
  }
  return { fields: {}, form: issueWriteErrorMessage(error) };
}

/**
 * Tạo issue (Leader). Khóa `Idempotency-Key` sinh khi mở; gửi lại sau lỗi dùng cùng khóa với cùng nội dung,
 * còn sửa ô nào sau lỗi thì sinh khóa mới vì nội dung đã khác.
 *
 * Có `activeSprint` (mở từ Board): mặc định thêm issue vào Sprint đang chạy để issue hiện ngay trên Board.
 * Backend không có lệnh "tạo trong sprint", nên đây là hai bước: tạo rồi thêm vào sprint (kèm lý do đổi phạm vi).
 * Bước thêm lỗi thì issue vẫn đã tạo, nằm ở Product Backlog: báo rõ và đóng dialog, không gửi lại lệnh tạo.
 */
export function CreateIssueDialog({
  projectId,
  open,
  onOpenChange,
  epics,
  assignees,
  activeSprint = null,
}: Readonly<{
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  epics: readonly Epic[];
  assignees: readonly { userId: string; name: string }[];
  activeSprint?: { id: string; name: string } | null;
}>) {
  const createTask = useCreateTask(projectId);
  const addToSprint = useAddTaskToSprint();
  const { reset } = createTask;
  const [values, setValues] = useState<IssueFormValues>(EMPTY_ISSUE_FORM);
  const [clientErrors, setClientErrors] = useState<IssueFormErrors>({});
  const [key, setKey] = useState(newIdempotencyKey);
  const [submitFailed, setSubmitFailed] = useState(false);
  const [intoSprint, setIntoSprint] = useState(true);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setValues(EMPTY_ISSUE_FORM);
    setClientErrors({});
    setKey(newIdempotencyKey());
    setSubmitFailed(false);
    setIntoSprint(true);
    setReason("");
    setReasonError(null);
    reset();
  }, [open, reset]);

  const addingToSprint = activeSprint !== null && intoSprint;
  const pending = createTask.isPending || addToSprint.isPending;

  function change(patch: Partial<IssueFormValues>) {
    setValues((current) => ({ ...current, ...patch }));
    setClientErrors({});
    if (submitFailed) {
      setKey(newIdempotencyKey());
      setSubmitFailed(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateIssueForm(values);
    setClientErrors(errors);
    const missingReason = addingToSprint && !reason.trim();
    setReasonError(missingReason ? "Nhập lý do thêm issue vào Sprint đang chạy." : null);
    if (Object.keys(errors).length > 0 || missingReason) return;

    let task;
    try {
      task = await createTask.mutateAsync({ ...toCreateInput(values), idempotencyKey: key });
    } catch {
      setSubmitFailed(true);
      return;
    }
    if (activeSprint !== null && addingToSprint) {
      try {
        await addToSprint.mutateAsync({ taskId: task.id, sprintId: activeSprint.id, reason: reason.trim() });
        toast.success(`Đã tạo ${task.code} trong ${activeSprint.name}.`);
      } catch (error) {
        toast.warning(
          `Đã tạo ${task.code} nhưng chưa thêm được vào Sprint: ${issueWriteErrorMessage(error)} Issue đang ở Product Backlog.`,
        );
      }
    } else {
      toast.success(`Đã tạo ${task.code} trong Product Backlog.`);
    }
    onOpenChange(false);
  }

  const server = createTask.error ? serverErrors(createTask.error) : null;
  const errors: IssueFormErrors = { ...server?.fields, ...clientErrors };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form className="space-y-4" onSubmit={(event) => void submit(event)}>
          <DialogHeader>
            <DialogTitle>Tạo issue</DialogTitle>
            <DialogDescription>
              {addingToSprint
                ? `Issue mới được thêm vào ${activeSprint.name} và hiện trên Board.`
                : "Issue mới vào Product Backlog; kéo vào Sprint ở trang Backlog để hiện trên Board."}
            </DialogDescription>
          </DialogHeader>

          {server?.form ? (
            <p className="text-sm text-destructive" role="alert">
              {server.form}
            </p>
          ) : null}

          {/* Khóa ô khi đang gửi: nội dung phải khớp `Idempotency-Key` đã gửi. */}
          <fieldset className="min-w-0 space-y-4" disabled={pending}>
            <IssueFormFields
              idPrefix="ci"
              values={values}
              onChange={change}
              errors={errors}
              epics={epics}
              assignees={assignees}
              showType
            />

            {activeSprint !== null ? (
              <div className="space-y-2 rounded-md border p-3">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="ci-into-sprint"
                    checked={intoSprint}
                    onCheckedChange={(checked) => {
                      setIntoSprint(checked === true);
                      setReasonError(null);
                    }}
                  />
                  <Label htmlFor="ci-into-sprint">Thêm vào Sprint đang chạy ({activeSprint.name})</Label>
                </div>
                {intoSprint ? (
                  <div className="space-y-1.5">
                    <Label htmlFor="ci-sprint-reason">Lý do thêm vào Sprint</Label>
                    <Textarea
                      id="ci-sprint-reason"
                      value={reason}
                      maxLength={REASON_MAX}
                      rows={2}
                      aria-invalid={reasonError ? true : undefined}
                      onChange={(event) => {
                        setReason(event.target.value);
                        setReasonError(null);
                      }}
                    />
                    <p className="text-xs text-muted-foreground">Thay đổi phạm vi Sprint đang chạy được ghi vào lịch sử cùng lý do.</p>
                    {reasonError ? (
                      <p className="text-xs text-destructive" role="alert">
                        {reasonError}
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </fieldset>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
              Hủy
            </Button>
            <Button type="submit" disabled={!values.title.trim() || pending}>
              {pending ? "Đang tạo..." : "Tạo Issue"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
