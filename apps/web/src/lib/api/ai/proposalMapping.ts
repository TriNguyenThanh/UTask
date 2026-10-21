import type { AiBacklogItemDto, AiSubtaskDto } from "@/lib/api/ai/dto";
import type { CreateTaskInput, TaskFieldsInput } from "@/lib/api/work/endpoints";
import type { TaskPriorityDto } from "@/lib/api/work/dto";

export const AI_PRIORITY: Record<AiBacklogItemDto["priority"], TaskPriorityDto> = {
  low: "LOW",
  medium: "MEDIUM",
  high: "HIGH",
  critical: "URGENT",
};

const TITLE_MAX = 300;

interface Suggestion {
  description: string;
  acceptance_criteria: string[];
  estimate_points: number;
}

/** Chỉ đặt khóa có nội dung: backend không nhận khóa rỗng cho thành viên thường. */
function textFields(source: Suggestion, title: string): TaskFieldsInput & { title: string } {
  const input: TaskFieldsInput & { title: string } = { title: title.trim().slice(0, TITLE_MAX) };
  const description = source.description.trim();
  if (description) input.descriptionHtml = description;
  const criteria = source.acceptance_criteria
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
  if (criteria) input.acceptanceCriteria = criteria;
  return input;
}

/**
 * Người không phải Leader chỉ được gửi title/mô tả/tiêu chí (backend trả 403 `LEADER_PERMISSION_REQUIRED`
 * nếu gửi thêm); điểm ước lượng chỉ gửi cho Leader.
 */
export function subtaskToCreateInput(source: AiSubtaskDto, title: string, isLeader: boolean) {
  const input = textFields(source, title);
  if (isLeader) input.storyPoints = Math.round(source.estimate_points);
  return input;
}

export function backlogItemToCreateInput(source: AiBacklogItemDto, title: string): CreateTaskInput {
  return {
    ...textFields(source, title),
    type: "TASK",
    priority: AI_PRIORITY[source.priority],
    storyPoints: Math.round(source.estimate_points),
  };
}
