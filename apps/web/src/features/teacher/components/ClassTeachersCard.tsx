import { useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import type { PublicUserDto } from "@/lib/api/identity/dto";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { ClassroomCourseDetail } from "@/lib/api/teacherFlow";
import { useAssignTeacher, useUserLookup } from "@/lib/query/teacherClassHooks";

const uuid = z.uuid();

/**
 * Thêm giảng viên đồng phụ trách. Chưa có API tra theo e-mail (B9) nên nhập mã
 * người dùng (UUID); tên tra được hiện ra để xác nhận đúng người trước khi phân công.
 */
export function ClassTeachersCard({ course }: Readonly<{ course: ClassroomCourseDetail }>) {
  const assign = useAssignTeacher(course.courseId);
  const lookup = useUserLookup();
  const [userId, setUserId] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<{ user: PublicUserDto; key: string } | null>(null);

  function find() {
    const id = userId.trim();
    if (!uuid.safeParse(id).success) {
      setInputError("Mã người dùng phải là UUID hợp lệ.");
      return;
    }
    setInputError(null);
    lookup.mutate(id, {
      onSuccess: (user) => {
        if (user) setCandidate({ user, key: newIdempotencyKey() });
        else setInputError("Không tìm thấy người dùng với mã này.");
      },
      onError: () => setInputError("Không tra cứu được người dùng. Vui lòng thử lại."),
    });
  }

  function confirm() {
    if (!candidate) return;
    assign.mutate(
      {
        version: course.classroom.version,
        userId: candidate.user.id,
        role: "CO_TEACHER",
        status: "ACTIVE",
        idempotencyKey: candidate.key,
      },
      {
        onSuccess: () => {
          toast.success(`Đã thêm ${candidate.user.display_name} vào lớp.`);
          setCandidate(null);
          setUserId("");
        },
        onError: (error) => {
          toast.error(classErrorMessage(error));
          setCandidate(null);
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Giảng viên phụ trách</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-1 text-sm">
          {course.instructors.map((instructor) => (
            <li key={instructor.userId} className="flex items-center gap-2">
              {instructor.name}
              {instructor.isOwner ? <Badge variant="secondary">Phụ trách chính</Badge> : null}
            </li>
          ))}
        </ul>

        <form
          className="space-y-2 border-t pt-4"
          onSubmit={(event) => {
            event.preventDefault();
            find();
          }}
        >
          <Label htmlFor="teacher-user-id">Thêm giảng viên đồng phụ trách</Label>
          <div className="flex flex-wrap gap-2">
            <Input
              id="teacher-user-id"
              className="max-w-md font-mono"
              placeholder="Mã người dùng (UUID)"
              value={userId}
              aria-invalid={inputError ? true : undefined}
              onChange={(event) => setUserId(event.target.value)}
            />
            <Button type="submit" variant="outline" disabled={lookup.isPending}>
              Tra cứu
            </Button>
          </div>
          {inputError ? (
            <p role="alert" className="text-xs text-destructive">
              {inputError}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Người được thêm cần có tài khoản giảng viên đang hoạt động.
            </p>
          )}
        </form>
      </CardContent>

      <ConfirmDialog
        open={candidate !== null}
        title="Thêm giảng viên vào lớp?"
        description={
          candidate
            ? `${candidate.user.display_name} (${candidate.user.email}) sẽ là giảng viên đồng phụ trách và quản lý được lớp này.`
            : ""
        }
        confirmLabel="Thêm giảng viên"
        pending={assign.isPending}
        onConfirm={confirm}
        onCancel={() => setCandidate(null)}
      />
    </Card>
  );
}
