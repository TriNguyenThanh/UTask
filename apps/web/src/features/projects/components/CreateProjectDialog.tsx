import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
import { Textarea } from "@/components/ui/textarea";
import { FieldError } from "@/features/notifications/components/FieldError";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useCreateProject } from "@/lib/query/workHooks";

const FIELD_ERROR_KEYS = ["identifier", "name", "start_date", "end_date"];

/** Ánh xạ mã lỗi → thông báo UI. */
function mapError(error: ApiError): {
  form?: string;
  identifier?: string[];
  name?: string[];
  start_date?: string[];
  end_date?: string[];
} {
  switch (error.code) {
    case "DUPLICATE_IDENTIFIER":
      return { identifier: ["Mã dự án đã được dùng. Hãy chọn mã khác."] };
    case "LEADER_PERMISSION_REQUIRED":
      return { form: "Chỉ trưởng nhóm mới tạo được dự án." };
    case "CLASSROOM_UNAVAILABLE":
      return { form: "Chưa xác minh được nhóm lớp học. Hãy thử lại sau ít phút." };
    case "CONCURRENT_MUTATION_IN_PROGRESS":
    case "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD":
      return { form: "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại." };
    case "VALIDATION_ERROR": {
      // Lỗi của ô không hiển thị riêng (hoặc `details` rỗng) phải hiện ở đầu form, không được mất.
      const shownOnField = Object.keys(error.fieldErrors).every((field) => FIELD_ERROR_KEYS.includes(field));
      return {
        identifier: error.fieldErrors.identifier,
        name: error.fieldErrors.name,
        start_date: error.fieldErrors.start_date,
        end_date: error.fieldErrors.end_date,
        form: Object.keys(error.fieldErrors).length > 0 && shownOnField ? undefined : error.message,
      };
    }
    default:
      return { form: error.message };
  }
}

export function CreateProjectDialog({
  groupId,
  open,
  onOpenChange,
}: Readonly<{ groupId: string; open: boolean; onOpenChange: (open: boolean) => void }>) {
  const navigate = useNavigate();
  const createProject = useCreateProject();

  const [identifier, setIdentifier] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [targetGoals, setTargetGoals] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);
  /** Sau khi gửi lỗi một lần, đổi bất kỳ ô nào → sinh khóa mới. */
  const [submitFailed, setSubmitFailed] = useState(false);

  // Khi dialog mở lại, sinh khóa mới và xóa form.
  useEffect(() => {
    if (open) {
      setIdentifier("");
      setName("");
      setDescription("");
      setTargetGoals("");
      setStartDate("");
      setEndDate("");
      setIdempotencyKey(newIdempotencyKey());
      setSubmitFailed(false);
      createProject.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function markFieldChange() {
    if (submitFailed) {
      setIdempotencyKey(newIdempotencyKey());
      setSubmitFailed(false);
    }
  }

  // Lỗi phía client để gán vào từng ô
  const [clientIdentifierError, setClientIdentifierError] = useState<string | undefined>();
  const [clientNameError, setClientNameError] = useState<string | undefined>();
  const [clientEndDateError, setClientEndDateError] = useState<string | undefined>();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Reset client errors
    setClientIdentifierError(undefined);
    setClientNameError(undefined);
    setClientEndDateError(undefined);

    // Validate identifier
    if (!/^[A-Z0-9]{2,10}$/.test(identifier)) {
      setClientIdentifierError("Mã dự án phải gồm 2–10 chữ in hoa hoặc số.");
      return;
    }
    if (!name.trim()) {
      setClientNameError("Tên dự án không được để trống.");
      return;
    }
    if (name.trim().length > 200) {
      setClientNameError("Tên dự án không được vượt quá 200 ký tự.");
      return;
    }
    if (startDate && endDate && endDate < startDate) {
      setClientEndDateError("Ngày kết thúc không được trước ngày bắt đầu.");
      return;
    }

    createProject.mutate(
      {
        classroomGroupId: groupId,
        identifier,
        name: name.trim(),
        description,
        targetGoals,
        startDate: startDate || null,
        endDate: endDate || null,
        idempotencyKey,
      },
      {
        onSuccess: (project) => {
          toast.success("Đã tạo dự án.");
          onOpenChange(false);
          void navigate(`/projects/${project.id}/info`);
        },
        onError: () => {
          setSubmitFailed(true);
        },
      },
    );
  }

  const serverError = createProject.error instanceof ApiError ? createProject.error : null;
  const mapped = serverError ? mapError(serverError) : {};
  const identifierErrors = mapped.identifier ?? (clientIdentifierError ? [clientIdentifierError] : undefined);
  const nameErrors = mapped.name ?? (clientNameError ? [clientNameError] : undefined);
  const endDateErrors = mapped.end_date ?? (clientEndDateError ? [clientEndDateError] : undefined);
  const startDateErrors = mapped.start_date;
  const formError = mapped.form;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <form className="space-y-4" onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Tạo dự án mới</DialogTitle>
            <DialogDescription>
              Nhóm bạn sẽ trở thành nhóm thực hiện dự án này.
            </DialogDescription>
          </DialogHeader>

          {formError ? (
            <p className="text-sm text-destructive" role="alert">
              {formError}
            </p>
          ) : null}

          {/* Khóa ô khi đang gửi: body phải khớp `Idempotency-Key` đã gửi. */}
          <fieldset className="min-w-0 space-y-4" disabled={createProject.isPending}>
          {/* Identifier */}
          <div className="space-y-1.5">
            <Label htmlFor="cp-identifier">Mã dự án</Label>
            <Input
              id="cp-identifier"
              value={identifier}
              onChange={(e) => {
                setIdentifier(e.target.value.toUpperCase());
                setClientIdentifierError(undefined);
                markFieldChange();
              }}
              placeholder="VD: NEXUS"
              maxLength={10}
              autoComplete="off"
              aria-invalid={identifierErrors ? true : undefined}
            />
            <p className="text-xs text-muted-foreground">
              2–10 chữ in hoa hoặc số, duy nhất toàn hệ thống.
            </p>
            <FieldError messages={identifierErrors} />
          </div>

          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="cp-name">Tên dự án</Label>
            <Input
              id="cp-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setClientNameError(undefined);
                markFieldChange();
              }}
              placeholder="VD: Hệ thống quản lý đồ án"
              maxLength={200}
              autoComplete="off"
              aria-invalid={nameErrors ? true : undefined}
            />
            <FieldError messages={nameErrors} />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="cp-description">Mô tả</Label>
            <Textarea
              id="cp-description"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                markFieldChange();
              }}
              placeholder="Mô tả ngắn về dự án..."
              rows={3}
            />
          </div>

          {/* Target goals */}
          <div className="space-y-1.5">
            <Label htmlFor="cp-target-goals">Mục tiêu dự án</Label>
            <Textarea
              id="cp-target-goals"
              value={targetGoals}
              onChange={(e) => {
                setTargetGoals(e.target.value);
                markFieldChange();
              }}
              placeholder="Các mục tiêu cần đạt được..."
              rows={3}
            />
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="cp-start-date">Ngày bắt đầu</Label>
              <Input
                id="cp-start-date"
                type="date"
                value={startDate}
                onChange={(e) => {
                  setStartDate(e.target.value);
                  setClientEndDateError(undefined);
                  markFieldChange();
                }}
              />
              <FieldError messages={startDateErrors} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cp-end-date">Ngày kết thúc</Label>
              <Input
                id="cp-end-date"
                type="date"
                value={endDate}
                onChange={(e) => {
                  setEndDate(e.target.value);
                  setClientEndDateError(undefined);
                  markFieldChange();
                }}
                aria-invalid={endDateErrors ? true : undefined}
              />
              <FieldError messages={endDateErrors} />
            </div>
          </div>
          </fieldset>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createProject.isPending}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={!identifier || !name.trim() || createProject.isPending}
            >
              {createProject.isPending ? "Đang tạo..." : "Tạo dự án"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
