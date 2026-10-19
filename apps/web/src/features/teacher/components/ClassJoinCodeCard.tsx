import { KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CopyJoinCodeButton } from "@/features/teacher/components/JoinCode";
import { formatDateTime } from "@/features/teacher/components/shared";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { ClassroomCourseDetail } from "@/lib/api/teacherFlow";
import { useIssueClassJoinCode } from "@/lib/query/teacherClassHooks";

type Pending = { enabled: boolean; key: string };

/**
 * Mã tham gia lớp. Backend chỉ lưu băm nên mã thô chỉ hiện đúng một lần, ngay
 * sau khi cấp, và chỉ nằm trong state của component này (mất khi rời trang).
 */
export function ClassJoinCodeCard({ course }: Readonly<{ course: ClassroomCourseDetail }>) {
  const { version, joinCodeExpiresAt } = course.classroom;
  const issue = useIssueClassJoinCode(course.courseId);
  const [shownCode, setShownCode] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const active = joinCodeExpiresAt !== null && new Date(joinCodeExpiresAt).getTime() > Date.now();

  function confirm() {
    if (!pending) return;
    issue.mutate(
      { version, enabled: pending.enabled, idempotencyKey: pending.key },
      {
        onSuccess: (result) => {
          setShownCode(pending.enabled ? (result.code ?? null) : null);
          toast.success(pending.enabled ? "Đã cấp mã tham gia mới." : "Đã tắt mã tham gia.");
          setPending(null);
        },
        onError: (error) => {
          toast.error(classErrorMessage(error));
          setPending(null);
        },
      },
    );
  }

  function issueNow() {
    // Chưa có mã đang dùng nên không cần xác nhận; vẫn một khóa cho mỗi lần bấm.
    issue.mutate(
      { version, enabled: true, idempotencyKey: newIdempotencyKey() },
      {
        onSuccess: (result) => {
          setShownCode(result.code ?? null);
          toast.success("Đã cấp mã tham gia mới.");
        },
        onError: (error) => toast.error(classErrorMessage(error)),
      },
    );
  }

  const enabling = pending?.enabled ?? true;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4 text-primary" aria-hidden /> Mã tham gia
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {active ? (
            <>
              <Badge variant="outline" className="border-emerald-300 bg-emerald-50 text-emerald-900">
                Đang bật
              </Badge>
              <span className="text-muted-foreground">
                Hết hạn {joinCodeExpiresAt ? formatDateTime(joinCodeExpiresAt) : ""}
              </span>
            </>
          ) : (
            <Badge variant="outline">Đang tắt hoặc đã hết hạn</Badge>
          )}
        </div>

        {shownCode ? (
          <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950">
            <p className="text-sm font-medium">Mã chỉ hiện một lần. Hãy sao chép và gửi cho sinh viên ngay.</p>
            <div className="flex items-center gap-2">
              <span aria-label="Mã tham gia vừa cấp" className="rounded-md border bg-background px-3 py-1.5 font-mono text-base font-semibold">
                {shownCode}
              </span>
              <CopyJoinCodeButton code={shownCode} />
            </div>
          </div>
        ) : null}

        {!shownCode && active ? (
          <p className="text-xs text-muted-foreground">
            Mã đang dùng không đọc lại được. Cần mã mới thì bấm "Tạo mã mới" (mã cũ ngừng dùng).
          </p>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => (active ? setPending({ enabled: true, key: newIdempotencyKey() }) : issueNow())}
          >
            Tạo mã mới
          </Button>
          {active ? (
            <Button type="button" variant="outline" onClick={() => setPending({ enabled: false, key: newIdempotencyKey() })}>
              Tắt mã
            </Button>
          ) : null}
        </div>
      </CardContent>

      <ConfirmDialog
        open={pending !== null}
        title={enabling ? "Tạo mã mới?" : "Tắt mã tham gia?"}
        description={
          enabling
            ? "Mã đang dùng sẽ ngừng hoạt động ngay. Sinh viên đã vào lớp không bị ảnh hưởng."
            : "Sinh viên mới không thể vào lớp bằng mã này nữa. Sinh viên đã vào lớp không bị ảnh hưởng."
        }
        confirmLabel={enabling ? "Tạo mã mới" : "Tắt mã"}
        destructive={!enabling}
        pending={issue.isPending}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </Card>
  );

}
