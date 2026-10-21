import { useState } from "react";
import { Navigate } from "react-router-dom";
import { isRealService } from "@/lib/config/services";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ApiError } from "@/lib/api/errors";
import { UNKNOWN_NAME } from "@/lib/api/classroom/teacherLoaders";
import { useRealProjectContext } from "@/features/projects/components/RealProjectLayout";
import { ProjectDashboardSection } from "@/features/projects/components/ProjectDashboard";
import { parseCapacity } from "@/features/projects/lib/capacity";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import { usePatchProject, useSetProjectArchived } from "@/lib/query/workHooks";
import { MemberGitHubCell } from "@/features/projects/components/MemberGitHubCell";
import { useAuth } from "@/features/auth/AuthProvider";
import { useSetMemberCapacity } from "@/lib/query/workSprintHooks";
import { useUserNames } from "@/lib/query/teacherClassHooks";
import type { ProjectDto, ProjectMemberDto } from "@/lib/api/work/dto";

/* ------------------------------------------------------------------ */
/* Error message helpers                                               */
/* ------------------------------------------------------------------ */

function patchErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return String(error);
  const { code } = error;
  if (code === "VERSION_CONFLICT") {
    return "Dự án đã được cập nhật bởi thao tác khác. Dữ liệu đã được tải lại, hãy thử lại.";
  }
  if (code === "CONCURRENT_MUTATION_IN_PROGRESS" || code === "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD") {
    return "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại.";
  }
  if (code === "INVALID_OPERATION") {
    return "Dự án đang ở chế độ chỉ đọc.";
  }
  return error.message;
}

function archiveErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return String(error);
  const { code } = error;
  if (code === "VERSION_CONFLICT") {
    return "Dự án đã được cập nhật bởi thao tác khác. Dữ liệu đã được tải lại, hãy thử lại.";
  }
  if (code === "CONCURRENT_MUTATION_IN_PROGRESS" || code === "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD") {
    return "Yêu cầu trước đó đang được xử lý, hãy chờ rồi thử lại.";
  }
  return error.message;
}

/* ------------------------------------------------------------------ */
/* Read-only info card                                                 */
/* ------------------------------------------------------------------ */

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

function ProjectInfoCard({ project }: { project: ProjectDto }) {
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <InfoRow label="Mã dự án" value={project.identifier} />
      <InfoRow label="Tên dự án" value={project.name} />
      <div className="sm:col-span-2">
        <InfoRow
          label="Mô tả"
          value={project.description.length > 0 ? project.description : "Chưa có mô tả"}
        />
      </div>
      <div className="sm:col-span-2">
        <InfoRow
          label="Mục tiêu"
          value={project.target_goals.length > 0 ? project.target_goals : "Chưa đặt"}
        />
      </div>
      <InfoRow label="Ngày bắt đầu" value={project.start_date ?? "Chưa đặt"} />
      <InfoRow label="Ngày kết thúc" value={project.end_date ?? "Chưa đặt"} />
      <InfoRow label="Ngày tạo" value={new Date(project.created_at).toLocaleDateString("vi-VN")} />
      <InfoRow label="Repository GitHub" value={project.github_repo_name ?? "Chưa kết nối"} />
      <InfoRow
        label="Trạng thái"
        value={project.archived_at !== null ? "Đã lưu trữ" : "Đang hoạt động"}
      />
    </dl>
  );
}

/* ------------------------------------------------------------------ */
/* Inline edit form                                                    */
/* ------------------------------------------------------------------ */

interface EditFormValues {
  name: string;
  description: string;
  target_goals: string;
  start_date: string;
  end_date: string;
}

function formValuesOf(project: ProjectDto): EditFormValues {
  return {
    name: project.name,
    description: project.description,
    target_goals: project.target_goals,
    start_date: project.start_date ?? "",
    end_date: project.end_date ?? "",
  };
}

function ProjectEditForm({
  project,
  projectId,
  onClose,
}: {
  project: ProjectDto;
  projectId: string;
  onClose: () => void;
}) {
  const patch = usePatchProject(projectId);
  const [values, setValues] = useState<EditFormValues>(() => formValuesOf(project));
  // Bản server mà form đang sửa. Khi tải lại ra version mới (sau VERSION_CONFLICT), nạp lại form theo
  // bản mới; nếu không, ô người dùng không đụng tới vẫn giữ giá trị cũ và bị gửi đè thay đổi của người khác.
  const [base, setBase] = useState(project);
  if (project.version !== base.version) {
    setBase(project);
    setValues(formValuesOf(project));
  }
  const [clientError, setClientError] = useState<{ field: string; message: string } | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  function set(field: keyof EditFormValues, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
    setClientError(null);
    setGeneralError(null);
  }

  function validate(): boolean {
    if (values.name.trim().length === 0 || values.name.length > 200) {
      setClientError({ field: "name", message: "Tên dự án phải từ 1 đến 200 ký tự." });
      return false;
    }
    if (values.start_date && values.end_date && values.end_date < values.start_date) {
      setClientError({ field: "end_date", message: "Ngày kết thúc không được trước ngày bắt đầu." });
      return false;
    }
    return true;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    // Only send changed fields (PatchProjectInput uses camelCase)
    const input: { name?: string; description?: string; targetGoals?: string; startDate?: string | null; endDate?: string | null; expectedVersion: number } = {
      expectedVersion: project.version,
    };
    if (values.name !== project.name) input.name = values.name;
    if (values.description !== project.description) input.description = values.description;
    if (values.target_goals !== project.target_goals) input.targetGoals = values.target_goals;
    const newStart = values.start_date || null;
    const newEnd = values.end_date || null;
    if (newStart !== project.start_date) input.startDate = newStart;
    if (newEnd !== project.end_date) input.endDate = newEnd;

    try {
      await patch.mutateAsync(input);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.details.length > 0) {
        // Field-level validation errors
        const first = err.details[0];
        if (first.field) {
          setClientError({ field: first.field, message: err.fieldErrors[first.field]?.[0] ?? err.message });
        } else {
          setGeneralError(err.message);
        }
      } else {
        setGeneralError(patchErrorMessage(err));
      }
    }
  }

  const apiFieldErrors = patch.error instanceof ApiError ? patch.error.fieldErrors : {};

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
      {generalError ? (
        <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{generalError}</p>
      ) : null}

      <div className="space-y-1">
        <Label htmlFor="edit-name">Tên dự án</Label>
        <Input
          id="edit-name"
          value={values.name}
          onChange={(e) => set("name", e.target.value)}
          maxLength={200}
        />
        {clientError?.field === "name" ? (
          <p className="text-xs text-destructive">{clientError.message}</p>
        ) : apiFieldErrors.name ? (
          <p className="text-xs text-destructive">{apiFieldErrors.name[0]}</p>
        ) : null}
      </div>

      <div className="space-y-1">
        <Label htmlFor="edit-description">Mô tả</Label>
        <Textarea
          id="edit-description"
          value={values.description}
          onChange={(e) => set("description", e.target.value)}
          rows={3}
        />
        {apiFieldErrors.description ? (
          <p className="text-xs text-destructive">{apiFieldErrors.description[0]}</p>
        ) : null}
      </div>

      <div className="space-y-1">
        <Label htmlFor="edit-target-goals">Mục tiêu</Label>
        <Textarea
          id="edit-target-goals"
          value={values.target_goals}
          onChange={(e) => set("target_goals", e.target.value)}
          rows={3}
        />
        {apiFieldErrors.target_goals ? (
          <p className="text-xs text-destructive">{apiFieldErrors.target_goals[0]}</p>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="edit-start-date">Ngày bắt đầu</Label>
          <Input
            id="edit-start-date"
            type="date"
            value={values.start_date}
            onChange={(e) => set("start_date", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="edit-end-date">Ngày kết thúc</Label>
          <Input
            id="edit-end-date"
            type="date"
            value={values.end_date}
            onChange={(e) => set("end_date", e.target.value)}
          />
          {clientError?.field === "end_date" ? (
            <p className="text-xs text-destructive">{clientError.message}</p>
          ) : apiFieldErrors.end_date ? (
            <p className="text-xs text-destructive">{apiFieldErrors.end_date[0]}</p>
          ) : null}
        </div>
      </div>

      <div className="flex gap-2">
        <Button type="submit" disabled={patch.isPending}>
          {patch.isPending ? "Đang lưu…" : "Lưu"}
        </Button>
        <Button type="button" variant="outline" onClick={onClose} disabled={patch.isPending}>
          Hủy
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Members table                                                       */
/* ------------------------------------------------------------------ */

const ROLE_LABEL: Record<string, string> = {
  LEADER: "Trưởng nhóm",
  MEMBER: "Thành viên",
};

/** Leader sửa số giờ/tuần ngay trong bảng; chỉ gửi khi giá trị hợp lệ và khác giá trị hiện tại. */
function CapacityCell({ projectId, member }: { projectId: string; member: ProjectMemberDto }) {
  const save = useSetMemberCapacity(projectId);
  const [text, setText] = useState(String(member.weekly_capacity));
  const [synced, setSynced] = useState(member.weekly_capacity);
  if (member.weekly_capacity !== synced) {
    setSynced(member.weekly_capacity);
    setText(String(member.weekly_capacity));
  }
  const parsed = parseCapacity(text);
  const changed = parsed !== null && parsed !== member.weekly_capacity;
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (parsed === null || !changed) return;
        save.mutate({ userId: member.user_id, weeklyCapacity: parsed });
      }}
    >
      <Input
        value={text}
        inputMode="numeric"
        className="h-8 w-20"
        aria-label={`Giờ/tuần của ${member.display_name || "thành viên"}`}
        aria-invalid={parsed === null ? true : undefined}
        disabled={save.isPending}
        onChange={(event) => setText(event.target.value)}
      />
      {changed ? (
        <Button type="submit" size="sm" disabled={save.isPending}>
          Lưu
        </Button>
      ) : null}
      {parsed === null ? <span className="text-xs text-destructive">Nhập số nguyên ≥ 0</span> : null}
      {save.error ? <span className="text-xs text-destructive">{issueWriteErrorMessage(save.error)}</span> : null}
    </form>
  );
}

function MembersTable({
  members,
  projectId,
  canEditCapacity,
  canRequestVerification,
}: {
  members: ProjectMemberDto[];
  projectId: string;
  canEditCapacity: boolean;
  canRequestVerification: boolean;
}) {
  const { user } = useAuth();
  const currentUserId = user?.id ?? null;
  const userIds = members.filter((m) => !m.display_name).map((m) => m.user_id);
  const namesQuery = useUserNames(userIds);

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">Thành viên đồng bộ từ nhóm lớp học.</p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Tên</th>
              <th className="px-4 py-2 text-left font-medium">Vai trò</th>
              <th className="px-4 py-2 text-left font-medium">Giờ/tuần</th>
              <th className="px-4 py-2 text-left font-medium">GitHub</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {members.map((member) => {
              const name =
                member.display_name.length > 0
                  ? member.display_name
                  : (namesQuery.data?.get(member.user_id) ?? UNKNOWN_NAME);
              return (
                <tr key={member.id}>
                  <td className="px-4 py-2">{name}</td>
                  <td className="px-4 py-2">
                    <Badge variant={member.role === "LEADER" ? "default" : "secondary"}>
                      {ROLE_LABEL[member.role] ?? member.role}
                    </Badge>
                  </td>
                  <td className="px-4 py-2">
                    {canEditCapacity ? <CapacityCell projectId={projectId} member={member} /> : member.weekly_capacity}
                  </td>
                  <td className="px-4 py-2">
                    <MemberGitHubCell
                      projectId={projectId}
                      member={member}
                      isSelf={member.user_id === currentUserId}
                      canRequestVerification={canRequestVerification}
                    />
                  </td>
                </tr>
              );
            })}
            {members.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                  Chưa có thành viên
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Route component                                                     */
/* ------------------------------------------------------------------ */

function RealProjectInfo() {
  const { projectId, shell } = useRealProjectContext();
  const { project, members, myRole, canEdit } = shell;
  const isArchived = project.archived_at !== null;
  const isLeader = myRole === "LEADER";

  const [editing, setEditing] = useState(false);
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const archive = useSetProjectArchived(projectId);

  async function handleArchive() {
    try {
      await archive.mutateAsync({ archived: !isArchived, expectedVersion: project.version });
      setArchiveDialogOpen(false);
    } catch (err) {
      // Đóng hộp xác nhận để thông báo lỗi bên dưới nút không bị lớp phủ che.
      setArchiveDialogOpen(false);
      setArchiveError(archiveErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6 p-4 md:p-6">
      {/* Info card */}
      <section className="rounded-md border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="font-semibold">Thông tin dự án</h2>
          {canEdit && !editing ? (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              Sửa thông tin
            </Button>
          ) : null}
        </div>
        <div className="p-4">
          {editing ? (
            <ProjectEditForm project={project} projectId={projectId} onClose={() => setEditing(false)} />
          ) : (
            <ProjectInfoCard project={project} />
          )}
        </div>
      </section>

      {/* Archive / unarchive */}
      {isLeader ? (
        <section className="rounded-md border bg-card">
          <div className="px-4 py-3">
            <h2 className="font-semibold">{isArchived ? "Mở lại dự án" : "Lưu trữ dự án"}</h2>
          </div>
          <div className="border-t px-4 py-4">
            {archiveError ? (
              <p className="mb-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{archiveError}</p>
            ) : null}
            <Button
              variant={isArchived ? "default" : "destructive"}
              onClick={() => {
                setArchiveError(null);
                setArchiveDialogOpen(true);
              }}
            >
              {isArchived ? "Mở lại dự án" : "Lưu trữ dự án"}
            </Button>
          </div>
        </section>
      ) : null}

      <ProjectDashboardSection projectId={projectId} members={members} />

      {/* Members */}
      <section className="rounded-md border bg-card">
        <div className="border-b px-4 py-3">
          <h2 className="font-semibold">Thành viên</h2>
        </div>
        <div className="p-4">
          <MembersTable
            members={members}
            projectId={projectId}
            canEditCapacity={isLeader && !isArchived}
            canRequestVerification={isLeader}
          />
        </div>
      </section>

      <ConfirmDialog
        open={archiveDialogOpen}
        title={isArchived ? "Mở lại dự án" : "Lưu trữ dự án"}
        description={
          isArchived
            ? "Dự án sẽ được chuyển về trạng thái hoạt động."
            : "Dự án sẽ được lưu trữ và không thể chỉnh sửa cho đến khi mở lại."
        }
        confirmLabel={isArchived ? "Mở lại" : "Lưu trữ"}
        destructive={!isArchived}
        pending={archive.isPending}
        onConfirm={() => void handleArchive()}
        onCancel={() => setArchiveDialogOpen(false)}
      />
    </div>
  );
}

export function Component() {
  return isRealService("work") ? <RealProjectInfo /> : <Navigate to="../board" relative="path" replace />;
}

export default Component;
