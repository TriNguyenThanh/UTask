import type { SprintDto } from "@/lib/api/work/dto";
import type { SprintFieldsInput } from "@/lib/api/work/endpoints";

export const SPRINT_NAME_MAX = 200;

export interface SprintFormValues {
  name: string;
  goal: string;
  /** `YYYY-MM-DD`; rỗng = chưa đặt. Sprint cần đủ hai ngày mới bắt đầu được. */
  startDate: string;
  endDate: string;
}

export const EMPTY_SPRINT_FORM: SprintFormValues = { name: "", goal: "", startDate: "", endDate: "" };

export type SprintFormErrors = Partial<Record<"name" | "endDate", string>>;

export function formValuesOfSprint(sprint: SprintDto): SprintFormValues {
  return {
    name: sprint.name,
    goal: sprint.goal,
    startDate: sprint.start_date ?? "",
    endDate: sprint.end_date ?? "",
  };
}

export function validateSprintForm(values: SprintFormValues): SprintFormErrors {
  const errors: SprintFormErrors = {};
  const name = values.name.trim();
  if (!name) errors.name = "Tên sprint không được để trống.";
  else if (name.length > SPRINT_NAME_MAX) errors.name = `Tên sprint không được vượt quá ${SPRINT_NAME_MAX} ký tự.`;
  if (values.startDate && values.endDate && values.startDate > values.endDate) {
    errors.endDate = "Ngày kết thúc không được trước ngày bắt đầu.";
  }
  return errors;
}

export function toCreateSprintInput(values: SprintFormValues): SprintFieldsInput & { name: string } {
  const input: SprintFieldsInput & { name: string } = { name: values.name.trim() };
  if (values.goal !== "") input.goal = values.goal;
  if (values.startDate !== "") input.startDate = values.startDate;
  if (values.endDate !== "") input.endDate = values.endDate;
  return input;
}

/** Chỉ khóa đã đổi; `null` khi không đổi gì. Xóa ngày gửi `null`. */
export function toPatchSprintInput(initial: SprintFormValues, current: SprintFormValues): SprintFieldsInput | null {
  const patch: SprintFieldsInput = {};
  if (current.name.trim() !== initial.name.trim()) patch.name = current.name.trim();
  if (current.goal !== initial.goal) patch.goal = current.goal;
  if (current.startDate !== initial.startDate) patch.startDate = current.startDate || null;
  if (current.endDate !== initial.endDate) patch.endDate = current.endDate || null;
  return Object.keys(patch).length === 0 ? null : patch;
}

/** Sprint nháp chỉ bắt đầu được khi đủ hai ngày (backend trả `INVALID_OPERATION` nếu thiếu). */
export function canStartSprint(sprint: Pick<SprintDto, "status" | "start_date" | "end_date">): boolean {
  return sprint.status === "DRAFT" && sprint.start_date !== null && sprint.end_date !== null;
}
