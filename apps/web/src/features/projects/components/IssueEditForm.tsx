import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { IssueFormFields } from "@/features/projects/components/IssueFormFields";
import {
  formValuesOfTask,
  toPatchInput,
  validateIssueForm,
  type IssueFormErrors,
  type IssueFormValues,
} from "@/features/projects/lib/issueForm";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { Epic } from "@/features/projects/types";
import { ApiError } from "@/lib/api/errors";
import type { TaskDto } from "@/lib/api/work/dto";
import { usePatchTask } from "@/lib/query/workWriteHooks";

export const VERSION_CONFLICT_MESSAGE =
  "Dữ liệu đã được cập nhật bởi thao tác khác. Dữ liệu đã được tải lại, hãy thử lại.";

/**
 * Form sửa issue (Work thật). `textOnly`: thành viên thường chỉ sửa title/mô tả/tiêu chí.
 * Khi `task.version` đổi (sau lưu hoặc sau tải lại vì xung đột) form nạp lại giá trị server,
 * nên lần lưu kế tiếp luôn gửi đúng `expected_version` mới.
 */
export function IssueEditForm({
  task,
  epics,
  assignees,
  textOnly,
}: Readonly<{
  task: TaskDto;
  epics: readonly Epic[];
  assignees: readonly { userId: string; name: string }[];
  textOnly: boolean;
}>) {
  const patch = usePatchTask(task.id);
  const [values, setValues] = useState<IssueFormValues>(() => formValuesOfTask(task));
  const [loadedVersion, setLoadedVersion] = useState(task.version);
  const [clientErrors, setClientErrors] = useState<IssueFormErrors>({});
  const [conflict, setConflict] = useState(false);

  useEffect(() => {
    if (task.version === loadedVersion) return;
    setValues(formValuesOfTask(task));
    setLoadedVersion(task.version);
    setClientErrors({});
  }, [task, loadedVersion]);

  const initial = formValuesOfTask(task);
  const changed = toPatchInput(initial, values, task.version, textOnly ? "text" : "all") !== null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validateIssueForm(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) return;
    const input = toPatchInput(initial, values, task.version, textOnly ? "text" : "all");
    if (!input) return;
    setConflict(false);
    patch.mutate(input, {
      onSuccess: () => toast.success("Đã lưu thay đổi."),
      onError: (error) => setConflict(error instanceof ApiError && error.code === "VERSION_CONFLICT"),
    });
  }

  const error = patch.error;
  const message = conflict ? VERSION_CONFLICT_MESSAGE : error ? issueWriteErrorMessage(error) : null;

  return (
    <form className="space-y-4" onSubmit={submit} aria-label="Sửa issue">
      {message ? (
        <p className="text-sm text-destructive" role="alert">
          {message}
        </p>
      ) : null}
      <fieldset className="min-w-0" disabled={patch.isPending}>
        <IssueFormFields
          idPrefix="ei"
          values={values}
          onChange={(change) => {
            setValues((current) => ({ ...current, ...change }));
            setClientErrors({});
          }}
          errors={clientErrors}
          epics={epics}
          assignees={assignees}
          textOnly={textOnly}
        />
      </fieldset>
      <Button type="submit" size="sm" disabled={!changed || patch.isPending}>
        {patch.isPending ? "Đang lưu..." : "Lưu thay đổi"}
      </Button>
    </form>
  );
}
