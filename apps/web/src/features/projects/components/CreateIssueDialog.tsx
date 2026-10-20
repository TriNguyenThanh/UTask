import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useCreateTask } from "@/lib/query/workWriteHooks";

const SHOWN_ON_FIELD = ["title", "story_points"];

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
 */
export function CreateIssueDialog({
  projectId,
  open,
  onOpenChange,
  epics,
  assignees,
}: Readonly<{
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  epics: readonly Epic[];
  assignees: readonly { userId: string; name: string }[];
}>) {
  const createTask = useCreateTask(projectId);
  const { reset } = createTask;
  const [values, setValues] = useState<IssueFormValues>(EMPTY_ISSUE_FORM);
  const [clientErrors, setClientErrors] = useState<IssueFormErrors>({});
  const [key, setKey] = useState(newIdempotencyKey);
  const [submitFailed, setSubmitFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValues(EMPTY_ISSUE_FORM);
    setClientErrors({});
    setKey(newIdempotencyKey());
    setSubmitFailed(false);
    reset();
  }, [open, reset]);

  function change(patch: Partial<IssueFormValues>) {
    setValues((current) => ({ ...current, ...patch }));
    setClientErrors({});
    if (submitFailed) {
      setKey(newIdempotencyKey());
      setSubmitFailed(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateIssueForm(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) return;
    createTask.mutate(
      { ...toCreateInput(values), idempotencyKey: key },
      {
        onSuccess: (task) => {
          toast.success(`Đã tạo ${task.code}.`);
          onOpenChange(false);
        },
        onError: () => setSubmitFailed(true),
      },
    );
  }

  const server = createTask.error ? serverErrors(createTask.error) : null;
  const errors: IssueFormErrors = { ...server?.fields, ...clientErrors };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form className="space-y-4" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Tạo issue</DialogTitle>
            <DialogDescription>Issue mới vào cột mặc định của Backlog.</DialogDescription>
          </DialogHeader>

          {server?.form ? (
            <p className="text-sm text-destructive" role="alert">
              {server.form}
            </p>
          ) : null}

          {/* Khóa ô khi đang gửi: nội dung phải khớp `Idempotency-Key` đã gửi. */}
          <fieldset className="min-w-0" disabled={createTask.isPending}>
            <IssueFormFields
              idPrefix="ci"
              values={values}
              onChange={change}
              errors={errors}
              epics={epics}
              assignees={assignees}
              showType
            />
          </fieldset>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={createTask.isPending}>
              Hủy
            </Button>
            <Button type="submit" disabled={!values.title.trim() || createTask.isPending}>
              {createTask.isPending ? "Đang tạo..." : "Tạo Issue"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
