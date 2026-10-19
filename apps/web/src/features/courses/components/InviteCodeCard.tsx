import { Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { groupErrorMessage } from "@/features/courses/lib/groupErrors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useIssueInviteCode } from "@/lib/query/classroomHooks";

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Trưởng nhóm cấp/tắt mã mời. Backend chỉ trả mã thô đúng một lần khi cấp, nên mã
 * chỉ nằm trong state của component này và mất khi rời trang; không lưu ở đâu khác.
 */
export function InviteCodeCard({
  groupId,
  version,
  expiresAt,
}: Readonly<{ groupId: string; version: number; expiresAt: string | null }>) {
  const issue = useIssueInviteCode(groupId);
  const [shownCode, setShownCode] = useState<string | null>(null);
  const active = expiresAt !== null && new Date(expiresAt).getTime() > Date.now();

  function run(enabled: boolean) {
    issue.mutate(
      { version, enabled, idempotencyKey: newIdempotencyKey() },
      {
        onSuccess: (result) => {
          setShownCode(enabled ? (result.code ?? null) : null);
          toast.success(enabled ? "Đã cấp mã mời mới." : "Đã tắt mã mời.");
        },
        onError: (error) => toast.error(groupErrorMessage(error)),
      },
    );
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Đã sao chép mã mời.");
    } catch {
      toast.error("Không sao chép được; hãy chép mã thủ công.");
    }
  }

  return (
    <section className="space-y-3 rounded-lg border p-4" aria-labelledby="invite-code-heading">
      <div className="flex items-center gap-2">
        <KeyRound className="size-4 text-primary" aria-hidden />
        <h2 id="invite-code-heading" className="text-base font-bold">
          Mã mời nhóm
        </h2>
      </div>
      <p className="text-xs text-muted-foreground">
        {active && expiresAt
          ? `Mã đang bật, hết hạn ${formatExpiry(expiresAt)}.`
          : "Mã mời đang tắt hoặc đã hết hạn."}
      </p>
      {shownCode ? (
        <div role="status" className="space-y-2 rounded-md bg-muted p-3">
          <div className="flex items-center gap-2">
            <code className="rounded bg-background px-2 py-1 font-mono text-sm font-semibold">{shownCode}</code>
            <Button type="button" size="xs" variant="outline" onClick={() => void copy(shownCode)}>
              <Copy className="size-3.5" aria-hidden />
              Sao chép
            </Button>
          </div>
          <p className="text-xs font-medium text-amber-700">
            Mã chỉ hiển thị một lần. Hãy sao chép ngay để gửi cho bạn học.
          </p>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => run(true)} disabled={issue.isPending}>
          {active ? "Tạo mã mới" : "Bật mã mời"}
        </Button>
        {active ? (
          <Button type="button" size="sm" variant="outline" onClick={() => run(false)} disabled={issue.isPending}>
            Tắt mã
          </Button>
        ) : null}
      </div>
    </section>
  );
}
