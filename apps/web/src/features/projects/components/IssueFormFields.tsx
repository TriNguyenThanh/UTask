import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FieldError } from "@/features/notifications/components/FieldError";
import {
  PRIORITY_OPTIONS,
  TITLE_MAX,
  type IssueFormErrors,
  type IssueFormType,
  type IssueFormValues,
} from "@/features/projects/lib/issueForm";
import type { Epic } from "@/features/projects/types";
import type { TaskPriorityDto } from "@/lib/api/work/dto";

const SELECT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

const TYPE_OPTIONS: readonly { value: IssueFormType; label: string }[] = [
  { value: "TASK", label: "Task" },
  { value: "STORY", label: "Story" },
  { value: "BUG", label: "Bug" },
];

/**
 * Các ô của form issue, dùng chung cho tạo mới và sửa. `textOnly`: thành viên thường chỉ sửa được
 * title, mô tả và tiêu chí nghiệm thu nên các ô còn lại bị ẩn. `idPrefix` giữ id ô duy nhất khi hai form cùng hiện.
 */
export function IssueFormFields({
  idPrefix,
  values,
  onChange,
  errors,
  epics,
  assignees,
  showType = false,
  textOnly = false,
}: Readonly<{
  idPrefix: string;
  values: IssueFormValues;
  onChange: (patch: Partial<IssueFormValues>) => void;
  errors: IssueFormErrors;
  epics: readonly Epic[];
  assignees: readonly { userId: string; name: string }[];
  showType?: boolean;
  textOnly?: boolean;
}>) {
  const id = (name: string) => `${idPrefix}-${name}`;
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor={id("title")}>Tiêu đề</Label>
        <Input
          id={id("title")}
          value={values.title}
          maxLength={TITLE_MAX}
          autoComplete="off"
          aria-invalid={errors.title ? true : undefined}
          onChange={(event) => onChange({ title: event.target.value })}
        />
        <FieldError messages={errors.title ? [errors.title] : undefined} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={id("description")}>Mô tả</Label>
        <Textarea
          id={id("description")}
          rows={3}
          value={values.description}
          onChange={(event) => onChange({ description: event.target.value })}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={id("criteria")}>Tiêu chí nghiệm thu</Label>
        <Textarea
          id={id("criteria")}
          rows={3}
          value={values.acceptanceCriteria}
          onChange={(event) => onChange({ acceptanceCriteria: event.target.value })}
        />
      </div>

      {textOnly ? null : (
        <>
          <div className="grid grid-cols-2 gap-4">
            {showType ? (
              <div className="space-y-1.5">
                <Label htmlFor={id("type")}>Loại</Label>
                <select
                  id={id("type")}
                  className={SELECT_CLASS}
                  value={values.type}
                  onChange={(event) => onChange({ type: event.target.value as IssueFormType })}
                >
                  {TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor={id("priority")}>Độ ưu tiên</Label>
              <select
                id={id("priority")}
                className={SELECT_CLASS}
                value={values.priority}
                onChange={(event) => onChange({ priority: event.target.value as TaskPriorityDto })}
              >
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={id("points")}>Story point</Label>
              <Input
                id={id("points")}
                inputMode="numeric"
                value={values.storyPoints}
                aria-invalid={errors.storyPoints ? true : undefined}
                onChange={(event) => onChange({ storyPoints: event.target.value })}
              />
              <FieldError messages={errors.storyPoints ? [errors.storyPoints] : undefined} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={id("due")}>Hạn chót</Label>
              <Input
                id={id("due")}
                type="date"
                value={values.dueDate}
                onChange={(event) => onChange({ dueDate: event.target.value })}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={id("epic")}>Epic</Label>
            <select
              id={id("epic")}
              className={SELECT_CLASS}
              value={values.epicId}
              onChange={(event) => onChange({ epicId: event.target.value })}
            >
              <option value="">Không thuộc epic</option>
              {epics.map((epic) => (
                <option key={epic.id} value={epic.id}>
                  {epic.name}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Người thực hiện</legend>
            {assignees.length === 0 ? (
              <p className="text-xs text-muted-foreground">Chưa có thành viên để giao việc.</p>
            ) : (
              <div className="grid grid-cols-2 gap-1.5">
                {assignees.map((member) => {
                  const checked = values.assigneeIds.includes(member.userId);
                  return (
                    <label key={member.userId} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          onChange({
                            assigneeIds: checked
                              ? values.assigneeIds.filter((userId) => userId !== member.userId)
                              : [...values.assigneeIds, member.userId],
                          })
                        }
                      />
                      {member.name}
                    </label>
                  );
                })}
              </div>
            )}
          </fieldset>
        </>
      )}
    </div>
  );
}
