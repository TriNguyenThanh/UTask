import type { ActivityDto } from "@/lib/api/work/dto";

/**
 * `old_value`/`new_value` là text thô, thường là JSON đã tuần tự hóa. Thử `JSON.parse`; không phải
 * JSON thì trả nguyên văn chuỗi. `null` (không có giá trị) giữ nguyên `null`.
 */
export function parseActivityValue(raw: string | null): unknown {
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

const MAX_VALUE_LENGTH = 80;

/** Dạng đọc được của một giá trị đã parse; chuỗi dài bị cắt để dòng lịch sử không tràn. */
export function formatActivityValue(value: unknown): string {
  let text: string;
  if (value === null || value === undefined || value === "") text = "(trống)";
  else if (typeof value === "string") text = value;
  else if (Array.isArray(value)) text = value.length === 0 ? "(trống)" : value.map((item) => formatActivityValue(item)).join(", ");
  else if (typeof value === "object") text = JSON.stringify(value);
  else text = String(value);
  return text.length > MAX_VALUE_LENGTH ? `${text.slice(0, MAX_VALUE_LENGTH - 1)}…` : text;
}

const FIELD_LABELS: Record<string, string> = {
  title: "tiêu đề",
  description_html: "mô tả",
  acceptance_criteria: "tiêu chí chấp nhận",
  state_id: "trạng thái",
  priority: "độ ưu tiên",
  story_points: "điểm",
  due_date: "hạn chót",
  epic_id: "epic",
  assignee_ids: "người thực hiện",
  label_ids: "nhãn",
  is_blocked: "trạng thái chặn",
  blocked_reason: "lý do chặn",
  sort_order: "thứ tự",
};

const VERB_LABELS: Record<string, string> = {
  created: "đã tạo",
  deleted: "đã xóa",
  restored: "đã khôi phục",
  archived: "đã lưu trữ",
  unarchived: "đã mở lại",
};

/** Tên hiển thị theo id cho các trường tham chiếu; id không tra được giữ nguyên. */
export type ActivityLookup = Partial<Record<string, (id: string) => string | undefined>>;

function resolveIds(value: unknown, resolve: ((id: string) => string | undefined) | undefined): unknown {
  if (!resolve) return value;
  if (typeof value === "string") return resolve(value) ?? value;
  if (Array.isArray(value)) return value.map((item) => resolveIds(item, resolve));
  return value;
}

/** Câu mô tả một dòng lịch sử, không kèm tên người thực hiện. Verb lạ được giữ nguyên để không mất thông tin. */
export function describeActivity(
  activity: Pick<ActivityDto, "verb" | "field" | "old_value" | "new_value">,
  lookup: ActivityLookup = {},
): string {
  const resolve = activity.field ? lookup[activity.field] : undefined;
  const field = activity.field ? (FIELD_LABELS[activity.field] ?? activity.field) : null;
  const hasChange = activity.old_value !== null || activity.new_value !== null;

  if (activity.verb === "updated" || (field !== null && hasChange)) {
    const label = field ?? "dữ liệu";
    if (!hasChange) return `đã cập nhật ${label}`;
    const before = formatActivityValue(resolveIds(parseActivityValue(activity.old_value), resolve));
    const after = formatActivityValue(resolveIds(parseActivityValue(activity.new_value), resolve));
    return `đã đổi ${label}: ${before} → ${after}`;
  }
  const verb = VERB_LABELS[activity.verb] ?? activity.verb;
  return field ? `${verb} ${field}` : verb;
}
