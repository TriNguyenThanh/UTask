import type { TaskDto, TaskPriorityDto } from "@/lib/api/work/dto";
import type { CreateTaskInput, PatchTaskInput } from "@/lib/api/work/endpoints";

export type IssueFormType = "TASK" | "BUG" | "STORY";

export interface IssueFormValues {
  type: IssueFormType;
  title: string;
  description: string;
  acceptanceCriteria: string;
  priority: TaskPriorityDto;
  /** Chuỗi nhập; rỗng = chưa ước lượng. */
  storyPoints: string;
  /** `YYYY-MM-DD`; rỗng = không hạn. */
  dueDate: string;
  /** Rỗng = không thuộc epic. */
  epicId: string;
  assigneeIds: string[];
}

export const EMPTY_ISSUE_FORM: IssueFormValues = {
  type: "TASK",
  title: "",
  description: "",
  acceptanceCriteria: "",
  priority: "MEDIUM",
  storyPoints: "",
  dueDate: "",
  epicId: "",
  assigneeIds: [],
};

export const TITLE_MAX = 300;

export type IssueFormErrors = Partial<Record<"title" | "storyPoints", string>>;

/** Nhãn priority: `URGENT` có nhãn riêng thay vì bị gộp vào "Cao". */
export const PRIORITY_OPTIONS: readonly { value: TaskPriorityDto; label: string }[] = [
  { value: "LOW", label: "Thấp" },
  { value: "MEDIUM", label: "Trung bình" },
  { value: "HIGH", label: "Cao" },
  { value: "URGENT", label: "Khẩn cấp" },
];

/** `description_html` được gửi nguyên văn từ textarea: không đọc/ghi HTML, chỉ hiển thị `description_stripped`. */
export function formValuesOfTask(task: TaskDto): IssueFormValues {
  return {
    type: task.type === "BUG" || task.type === "STORY" ? task.type : "TASK",
    title: task.title,
    description: task.description_stripped,
    acceptanceCriteria: task.acceptance_criteria,
    priority: task.priority,
    storyPoints: task.story_points === null ? "" : String(task.story_points),
    dueDate: task.due_date ?? "",
    epicId: task.epic_id ?? "",
    assigneeIds: [...task.assignee_ids],
  };
}

export function validateIssueForm(values: IssueFormValues): IssueFormErrors {
  const errors: IssueFormErrors = {};
  const title = values.title.trim();
  if (!title) errors.title = "Tiêu đề không được để trống.";
  else if (title.length > TITLE_MAX) errors.title = `Tiêu đề không được vượt quá ${TITLE_MAX} ký tự.`;
  if (values.storyPoints.trim() !== "" && !/^\d{1,9}$/.test(values.storyPoints.trim())) {
    errors.storyPoints = "Story point phải là số nguyên không âm.";
  }
  return errors;
}

function storyPointsOf(values: IssueFormValues): number | null {
  const text = values.storyPoints.trim();
  return text === "" ? null : Number(text);
}

/** Chỉ gửi ô có giá trị: server tự điền mặc định, nên form trống không tạo khóa thừa. */
export function toCreateInput(values: IssueFormValues): CreateTaskInput {
  const input: CreateTaskInput = { title: values.title.trim(), type: values.type, priority: values.priority };
  if (values.description !== "") input.descriptionHtml = values.description;
  if (values.acceptanceCriteria !== "") input.acceptanceCriteria = values.acceptanceCriteria;
  const points = storyPointsOf(values);
  if (points !== null) input.storyPoints = points;
  if (values.dueDate !== "") input.dueDate = values.dueDate;
  if (values.epicId !== "") input.epicId = values.epicId;
  if (values.assigneeIds.length > 0) input.assigneeIds = values.assigneeIds;
  return input;
}

const sameSet = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((id) => b.includes(id));

/**
 * Chỉ khóa đã đổi so với `initial`; `null` khi không đổi gì. `allowed` giới hạn khóa gửi đi:
 * `"text"` (thành viên thường) chỉ được sửa mô tả, khớp `require_member_fields(.., {"description_html"})` của backend.
 */
export function toPatchInput(
  initial: IssueFormValues,
  current: IssueFormValues,
  expectedVersion: number,
  allowed: "all" | "text" = "all",
): PatchTaskInput | null {
  const patch: PatchTaskInput = { expectedVersion };
  let changed = false;
  const set = <K extends keyof PatchTaskInput>(key: K, value: PatchTaskInput[K]) => {
    patch[key] = value;
    changed = true;
  };
  if (allowed === "all" && current.title.trim() !== initial.title.trim()) set("title", current.title.trim());
  if (current.description !== initial.description) set("descriptionHtml", current.description);
  if (allowed === "all" && current.acceptanceCriteria !== initial.acceptanceCriteria) {
    set("acceptanceCriteria", current.acceptanceCriteria);
  }
  if (allowed === "all") {
    if (current.priority !== initial.priority) set("priority", current.priority);
    if (current.storyPoints.trim() !== initial.storyPoints.trim()) set("storyPoints", storyPointsOf(current));
    if (current.dueDate !== initial.dueDate) set("dueDate", current.dueDate === "" ? null : current.dueDate);
    if (current.epicId !== initial.epicId) set("epicId", current.epicId === "" ? null : current.epicId);
    if (!sameSet(current.assigneeIds, initial.assigneeIds)) set("assigneeIds", current.assigneeIds);
  }
  return changed ? patch : null;
}
