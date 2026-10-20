export const LABEL_NAME_MAX = 50;

/** Thông báo lỗi của form nhãn, hoặc `null` khi hợp lệ. Màu phải là `#RRGGBB` như backend yêu cầu. */
export function validateLabelForm(values: { name: string; color: string }): string | null {
  const name = values.name.trim();
  if (!name) return "Tên nhãn không được để trống.";
  if (name.length > LABEL_NAME_MAX) return `Tên nhãn không được vượt quá ${LABEL_NAME_MAX} ký tự.`;
  if (!/^#[0-9A-Fa-f]{6}$/.test(values.color)) return "Màu nhãn phải có dạng #RRGGBB.";
  return null;
}
