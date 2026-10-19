import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/features/teacher/components/shared";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import type { ClassStatus } from "@/lib/api/classroom/dto";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { ClassroomCourseDetail } from "@/lib/api/teacherFlow";
import { useLockGrouping, useSetClassState } from "@/lib/query/teacherClassHooks";

const STATUS_LABEL: Record<ClassStatus, string> = {
  OPEN: "Đang mở",
  CLOSED: "Đã đóng",
  ARCHIVED: "Đã lưu trữ",
};

interface StateChange {
  status: ClassStatus;
  title: string;
  description: string;
  confirmLabel: string;
  destructive: boolean;
  success: string;
}

const CHANGES: Record<"close" | "reopen" | "archive", StateChange> = {
  close: {
    status: "CLOSED",
    title: "Đóng lớp?",
    description: "Lớp đóng sẽ không nhận thêm thao tác cần lớp đang mở (ví dụ sinh viên vào lớp bằng mã). Có thể mở lại sau.",
    confirmLabel: "Đóng lớp",
    destructive: false,
    success: "Đã đóng lớp.",
  },
  reopen: {
    status: "OPEN",
    title: "Mở lại lớp?",
    description: "Lớp sẽ nhận thao tác trở lại.",
    confirmLabel: "Mở lại lớp",
    destructive: false,
    success: "Đã mở lại lớp.",
  },
  archive: {
    status: "ARCHIVED",
    title: "Lưu trữ lớp?",
    description: "Lớp lưu trữ không thể mở lại. Hãy chắc chắn trước khi tiếp tục.",
    confirmLabel: "Lưu trữ lớp",
    destructive: true,
    success: "Đã lưu trữ lớp.",
  },
};

type Pending =
  | { kind: "state"; change: StateChange; key: string }
  | { kind: "lock"; key: string };

/** Trạng thái lớp và chốt giai đoạn lập nhóm. Cả hai đều hỏi xác nhận; chốt lập nhóm và lưu trữ không hoàn tác được. */
export function ClassStateCard({ course }: Readonly<{ course: ClassroomCourseDetail }>) {
  const { version, status, groupingPhase, groupingLockedAt } = course.classroom;
  const setState = useSetClassState(course.courseId);
  const lock = useLockGrouping(course.courseId);
  const [pending, setPending] = useState<Pending | null>(null);

  function ask(change: StateChange) {
    setPending({ kind: "state", change, key: newIdempotencyKey() });
  }

  function confirm() {
    if (!pending) return;
    const done = () => setPending(null);
    const failed = (error: unknown) => {
      toast.error(classErrorMessage(error));
      done();
    };
    if (pending.kind === "state") {
      setState.mutate(
        { version, status: pending.change.status, idempotencyKey: pending.key },
        {
          onSuccess: () => {
            toast.success(pending.change.success);
            done();
          },
          onError: failed,
        },
      );
    } else {
      lock.mutate(
        { version, idempotencyKey: pending.key },
        {
          onSuccess: () => {
            toast.success("Đã chốt giai đoạn lập nhóm.");
            done();
          },
          onError: failed,
        },
      );
    }
  }

  const dialog = pending
    ? pending.kind === "state"
      ? pending.change
      : {
          title: "Chốt giai đoạn lập nhóm?",
          description:
            "Sau khi chốt, sinh viên không tạo, vào hay rời nhóm được nữa và không có cách mở lại. Hãy chắc chắn mọi sinh viên đã có nhóm.",
          confirmLabel: "Chốt lập nhóm",
          destructive: true,
        }
    : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Trạng thái lớp</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{STATUS_LABEL[status]}</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            {status === "OPEN" ? (
              <Button type="button" variant="outline" onClick={() => ask(CHANGES.close)}>
                Đóng lớp
              </Button>
            ) : null}
            {status === "CLOSED" ? (
              <Button type="button" variant="outline" onClick={() => ask(CHANGES.reopen)}>
                Mở lại lớp
              </Button>
            ) : null}
            {status === "ARCHIVED" ? (
              <p className="text-sm text-muted-foreground">Lớp đã lưu trữ không thể mở lại.</p>
            ) : (
              <Button type="button" variant="outline" onClick={() => ask(CHANGES.archive)}>
                Lưu trữ lớp
              </Button>
            )}
          </div>
        </div>

        <div className="space-y-2 border-t pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Giai đoạn lập nhóm</h3>
            <Badge variant="outline">{groupingPhase === "LOCKED" ? "Đã chốt" : "Đang lập nhóm"}</Badge>
          </div>
          {groupingPhase === "LOCKED" ? (
            <p className="text-sm text-muted-foreground">
              {groupingLockedAt ? `Chốt lúc ${formatDateTime(groupingLockedAt)}. ` : ""}
              Sinh viên không còn tạo, vào hay rời nhóm được.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Sinh viên đang tự tạo và vào nhóm. Chốt khi hết hạn lập nhóm; không có cách mở lại.
              </p>
              <Button type="button" variant="outline" onClick={() => setPending({ kind: "lock", key: newIdempotencyKey() })}>
                Chốt lập nhóm
              </Button>
            </>
          )}
        </div>
      </CardContent>

      <ConfirmDialog
        open={dialog !== null}
        title={dialog?.title ?? ""}
        description={dialog?.description ?? ""}
        confirmLabel={dialog?.confirmLabel ?? ""}
        destructive={dialog?.destructive}
        pending={setState.isPending || lock.isPending}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </Card>
  );
}
