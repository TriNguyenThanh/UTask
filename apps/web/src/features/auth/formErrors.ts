import type { FieldPath, FieldValues, UseFormReturn } from "react-hook-form";

import type { ApiError } from "@/lib/api/errors";

/**
 * Đưa lỗi theo trường của backend vào react-hook-form. `fields` ánh xạ tên trường
 * backend → tên trường form. Trả về true khi có ít nhất một lỗi được gán.
 */
export function applyFieldErrors<T extends FieldValues>(
  form: UseFormReturn<T>,
  error: ApiError,
  fields: Record<string, FieldPath<T>>,
): boolean {
  let applied = false;
  for (const [backendField, formField] of Object.entries(fields)) {
    const messages = error.fieldErrors[backendField];
    if (messages?.length) {
      form.setError(formField, { message: messages.join(" ") });
      applied = true;
    }
  }
  return applied;
}
