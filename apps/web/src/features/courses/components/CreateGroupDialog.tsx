import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldError } from "@/features/notifications/components/FieldError";
import type { CourseDetail } from "@/features/courses/types";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useCreateGroup } from "@/lib/query/classroomHooks";

/**
 * Tạo nhóm ở chế độ Classroom thật. Cỡ nhóm cấu hình theo lớp nên không nhập ở đây;
 * mô tả và kỹ năng cần tuyển chưa có API.
 */
export function CreateGroupDialog({
  course,
  open,
  onOpenChange,
}: Readonly<{ course: CourseDetail; open: boolean; onOpenChange: (open: boolean) => void }>) {
  const createGroup = useCreateGroup(course.courseId);
  const [name, setName] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) {
      // Lần mở sau là ý định mới.
      setName("");
      setIdempotencyKey(newIdempotencyKey());
      createGroup.reset();
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createGroup.mutate(
      { name: name.trim(), idempotencyKey },
      {
        onSuccess: () => {
          toast.success("Tạo nhóm thành công. Bạn là Trưởng nhóm của nhóm mới.");
          handleOpenChange(false);
        },
      },
    );
  }

  const error = createGroup.error;
  const nameErrors = error instanceof ApiError ? error.fieldErrors.name : undefined;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Tạo nhóm mới</DialogTitle>
            <DialogDescription>
              Nhóm từ {course.teamSize.min} đến {course.teamSize.max} sinh viên. Bạn sẽ trở thành
              Trưởng nhóm sau khi tạo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="group-name">Tên nhóm</Label>
            <Input
              id="group-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="VD: Team NEXUS"
              maxLength={200}
              autoComplete="off"
              aria-invalid={error ? true : undefined}
            />
            <FieldError messages={nameErrors} />
            {error && !nameErrors ? (
              <p className="text-sm text-destructive" role="alert">
                {error.message}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={name.trim() === "" || createGroup.isPending}>
              {createGroup.isPending ? "Đang tạo..." : "Tạo nhóm"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
