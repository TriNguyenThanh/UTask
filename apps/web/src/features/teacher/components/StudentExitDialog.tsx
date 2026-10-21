import { toast } from "sonner";

import { ReasonDialog } from "@/components/feedback/ReasonDialog";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { TeacherStudent } from "@/lib/api/teacherFlow";
import { useExitEnrollment } from "@/lib/query/teacherClassHooks";

/**
 * Remove a student from the class (real Classroom only). The backend ends the
 * student's team membership too, but refuses while they are the team's Leader:
 * its message ("chuyển quyền trưởng nhóm trước") is shown as is.
 */
export function StudentExitDialog({
  classId,
  student,
  onClose,
}: Readonly<{ classId: string; student: TeacherStudent | null; onClose: () => void }>) {
  const exit = useExitEnrollment(classId);

  function confirm(reason: string) {
    if (!student?.enrollmentId) return;
    exit.mutate(
      { enrollmentId: student.enrollmentId, reason, idempotencyKey: newIdempotencyKey() },
      {
        onSuccess: () => toast.success(`Đã loại ${student.name || "sinh viên"} khỏi lớp.`),
        onError: (error) => toast.error(classErrorMessage(error)),
        onSettled: onClose,
      },
    );
  }

  return (
    <ReasonDialog
      open={student !== null}
      title={`Loại ${student?.name || "sinh viên"} khỏi lớp?`}
      description={
        student?.team?.role === "leader"
          ? `Sinh viên đang là Leader của ${student.team.name}. Hãy chỉ định Leader mới ở tab Nhóm trước, nếu không hệ thống sẽ từ chối.`
          : "Sinh viên mất quyền vào lớp và rời nhóm hiện tại. Lịch sử tham gia được giữ lại; lý do được ghi vào lịch sử lớp."
      }
      confirmLabel="Loại khỏi lớp"
      onConfirm={confirm}
      onCancel={onClose}
    />
  );
}
