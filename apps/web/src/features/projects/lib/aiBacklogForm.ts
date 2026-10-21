import type { AiBacklogRequest } from "@/lib/api/ai/dto";

export const DESCRIPTION_MAX = 12_000;
export const LIST_MAX = 30;

export interface BacklogFormValues {
  description: string;
  goals: string;
  techStack: string;
  constraints: string;
  extra: string;
}

export const EMPTY_BACKLOG_FORM: BacklogFormValues = { description: "", goals: "", techStack: "", constraints: "", extra: "" };

/** Mỗi dòng một mục: bỏ khoảng trắng và dòng rỗng. */
export function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Giá trị điền sẵn từ dự án: mô tả (hoặc tên nếu trống) và mục tiêu. `tech_stack` của Work là object tự do nên không điền. */
export function backlogFormFromProject(project: { name: string; description: string; target_goals: string }): BacklogFormValues {
  return {
    ...EMPTY_BACKLOG_FORM,
    description: project.description.trim() || project.name,
    goals: project.target_goals,
  };
}

export type BacklogFormErrors = Partial<Record<"description" | "goals" | "techStack" | "constraints", string>>;

/** Giới hạn của AI Service: mô tả bắt buộc, mỗi danh sách tối đa 30 mục. */
export function validateBacklogForm(values: BacklogFormValues): BacklogFormErrors {
  const errors: BacklogFormErrors = {};
  if (!values.description.trim()) errors.description = "Nhập mô tả dự án.";
  for (const [field, text] of [
    ["goals", values.goals],
    ["techStack", values.techStack],
    ["constraints", values.constraints],
  ] as const) {
    if (splitLines(text).length > LIST_MAX) errors[field] = `Tối đa ${LIST_MAX} mục.`;
  }
  return errors;
}

/**
 * Chỉ gửi khóa có nội dung (AI Service từ chối chuỗi rỗng). `deadline` cần múi giờ: hết ngày `end_date` theo giờ Việt Nam.
 */
export function buildBacklogBody(projectId: string, values: BacklogFormValues, endDate: string | null): AiBacklogRequest {
  const input: AiBacklogRequest["input"] = { description: values.description.trim().slice(0, DESCRIPTION_MAX) };
  const goals = splitLines(values.goals);
  const techStack = splitLines(values.techStack);
  const constraints = splitLines(values.constraints);
  if (goals.length > 0) input.goals = goals;
  if (techStack.length > 0) input.tech_stack = techStack;
  if (constraints.length > 0) input.constraints = constraints;
  if (endDate) input.deadline = `${endDate}T23:59:59+07:00`;
  if (values.extra.trim()) input.additional_instruction = values.extra.trim();
  return { intent: "backlog_generation", target: { type: "project", id: projectId }, input };
}
