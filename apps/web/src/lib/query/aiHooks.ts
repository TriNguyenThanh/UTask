import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api/ApiClientProvider";
import { applySequentially, type ApplyItem } from "@/lib/api/ai/applyProposal";
import type { AiRequestBody } from "@/lib/api/ai/dto";
import { runAiRequest } from "@/lib/api/ai/endpoints";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { workKeys } from "@/lib/query/workHooks";

/** Mỗi lần gọi là một ý định mới, nên mỗi lần một `Idempotency-Key`. */
export function useAiRequest<R>() {
  const client = useApiClient();
  return useMutation({
    mutationFn: ({ body, signal }: { body: AiRequestBody; signal: AbortSignal }) =>
      runAiRequest<R>(client, body, { idempotencyKey: newIdempotencyKey(), signal }),
  });
}

export interface ApplyVariables<I> {
  items: readonly ApplyItem<I>[];
  create: (input: I, idempotencyKey: string) => Promise<unknown>;
  onProgress?: (done: number, total: number) => void;
}

/**
 * Tạo hàng loạt rồi tải lại dữ liệu Work đúng một lần (không dùng `useCreateTask`/`useCreateSubtask`:
 * chúng tải lại sau từng item). Tải lại cả khi dừng giữa chừng vì một phần đã được tạo.
 */
export function useApplyProposal<I>() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ items, create, onProgress }: ApplyVariables<I>) => applySequentially(items, create, onProgress),
    onSettled: () => queryClient.invalidateQueries({ queryKey: workKeys.all }),
  });
}
