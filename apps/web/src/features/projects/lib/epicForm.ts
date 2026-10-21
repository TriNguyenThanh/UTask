import type { EpicDto, EpicStatusDto } from "@/lib/api/work/dto";
import type { EpicInput } from "@/lib/api/work/endpoints";

export const EPIC_NAME_MAX = 200;

export interface EpicFormValues {
  name: string;
  description: string;
  /** Rỗng = chưa có người phụ trách. */
  leadUserId: string;
  status: EpicStatusDto;
  /** `YYYY-MM-DD`; rỗng = chưa đặt. */
  startDate: string;
  targetDate: string;
}

export const EMPTY_EPIC_FORM: EpicFormValues = {
  name: "",
  description: "",
  leadUserId: "",
  status: "PLANNED",
  startDate: "",
  targetDate: "",
};

export const EPIC_STATUS_OPTIONS: readonly { value: EpicStatusDto; label: string }[] = [
  { value: "PLANNED", label: "Dự kiến" },
  { value: "IN_PROGRESS", label: "Đang thực hiện" },
  { value: "COMPLETED", label: "Hoàn thành" },
  { value: "CANCELLED", label: "Đã hủy" },
];

export type EpicFormErrors = Partial<Record<"name" | "targetDate", string>>;

export function formValuesOfEpic(epic: EpicDto): EpicFormValues {
  return {
    name: epic.name,
    description: epic.description,
    leadUserId: epic.lead_user_id ?? "",
    status: epic.status,
    startDate: epic.start_date ?? "",
    targetDate: epic.target_date ?? "",
  };
}

/** Backend trả `VALIDATION_ERROR` không chỉ ô nào cho thứ tự ngày, nên chặn trước khi gửi. */
export function validateEpicForm(values: EpicFormValues): EpicFormErrors {
  const errors: EpicFormErrors = {};
  const name = values.name.trim();
  if (!name) errors.name = "Tên epic không được để trống.";
  else if (name.length > EPIC_NAME_MAX) errors.name = `Tên epic không được vượt quá ${EPIC_NAME_MAX} ký tự.`;
  if (values.startDate && values.targetDate && values.startDate > values.targetDate) {
    errors.targetDate = "Ngày mục tiêu không được trước ngày bắt đầu.";
  }
  return errors;
}

export function toCreateEpicInput(values: EpicFormValues): EpicInput & { name: string } {
  const input: EpicInput & { name: string } = { name: values.name.trim(), status: values.status };
  if (values.description !== "") input.description = values.description;
  if (values.leadUserId !== "") input.leadUserId = values.leadUserId;
  if (values.startDate !== "") input.startDate = values.startDate;
  if (values.targetDate !== "") input.targetDate = values.targetDate;
  return input;
}

/**
 * Chỉ khóa đã đổi; `null` khi không đổi gì. `limited`: người phụ trách (không phải Leader) chỉ được sửa
 * tên, mô tả và trạng thái, gửi ô khác bị server từ chối.
 */
export function toPatchEpicInput(
  initial: EpicFormValues,
  current: EpicFormValues,
  allowed: "all" | "limited" = "all",
): EpicInput | null {
  const patch: EpicInput = {};
  if (current.name.trim() !== initial.name.trim()) patch.name = current.name.trim();
  if (current.description !== initial.description) patch.description = current.description;
  if (current.status !== initial.status) patch.status = current.status;
  if (allowed === "all") {
    if (current.leadUserId !== initial.leadUserId) patch.leadUserId = current.leadUserId === "" ? null : current.leadUserId;
    if (current.startDate !== initial.startDate) patch.startDate = current.startDate === "" ? null : current.startDate;
    if (current.targetDate !== initial.targetDate) patch.targetDate = current.targetDate === "" ? null : current.targetDate;
  }
  return Object.keys(patch).length > 0 ? patch : null;
}

/** Leader sửa mọi epic; người phụ trách chỉ sửa epic của mình. */
export function epicEditAccess(
  role: "leader" | "member" | "none",
  userId: string,
  epic: Pick<EpicDto, "lead_user_id">,
): "all" | "limited" | null {
  if (role === "leader") return "all";
  if (role === "member" && epic.lead_user_id === userId) return "limited";
  return null;
}
