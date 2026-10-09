import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  GitBranch,
  Hourglass,
  KanbanSquare,
  Search,
  UserPlus,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Badge } from "@/components/ui/badge";
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
import type {
  CourseDetail,
  OpenTeamSlot,
  TeamMember,
  TopicProposal,
  UnassignedClassmate,
} from "@/features/courses/types";
import { ApiError } from "@/lib/api/errors";
import { canCreateTeam, canSubmitTopic, type CoursePermissionContext } from "@/lib/permissions";
import { useCourseDetail, useCreateTeam } from "@/lib/query/studentFlowHooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).slice(-2);
  return parts.map((part) => part[0] ?? "").join("").toUpperCase();
}

function remainingTime(deadline: string): string {
  const ms = new Date(deadline).getTime() - Date.now();
  if (ms <= 0) return "Đã hết hạn";
  const hours = Math.ceil(ms / 3_600_000);
  if (hours >= 48) return `Còn ${Math.floor(hours / 24)} ngày`;
  if (hours >= 1) return `Còn ${hours} giờ`;
  return `Còn ${Math.max(1, Math.ceil(ms / 60_000))} phút`;
}

/* ------------------------------------------------------------------ */
/* View: membership.status === "none" (Team Formation)                 */
/* ------------------------------------------------------------------ */

function DeadlineBanner({ course }: Readonly<{ course: CourseDetail }>) {
  const deadline = course.teamFormation.registrationDeadline;
  if (!deadline) {
    return null;
  }
  const passed = new Date(deadline).getTime() <= Date.now();
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-md border-l-4 border-amber-500 bg-amber-50 px-4 py-3 text-sm",
        passed && "border-red-400 bg-red-50",
      )}
    >
      <Hourglass
        className={cn("mt-0.5 size-5 shrink-0", passed ? "text-red-600" : "text-amber-600")}
        aria-hidden
      />
      <p className={cn("flex flex-wrap items-center gap-x-2", passed ? "text-red-950" : "text-amber-950")}>
        <span className={cn("font-semibold", passed ? "text-red-900" : "text-amber-900")}>
          {passed
            ? `Hạn tự lập nhóm đã qua (${formatDateTime(deadline)}).`
            : `Hạn chót tự lập nhóm: ${remainingTime(deadline)} (${formatDateTime(deadline)}).`}
        </span>
        <span className={passed ? "text-red-800/90 text-[13px]" : "text-amber-800/90 text-[13px]"}>
          Sau thời hạn này, giảng viên sẽ xem xét phương án phân nhóm cho sinh viên chưa có nhóm.
        </span>
      </p>
    </div>
  );
}

function OpenTeamsSection({ openTeams }: Readonly<{ openTeams: OpenTeamSlot[] }>) {
  return (
    <section className="space-y-3 pt-2" aria-labelledby="open-teams-heading">
      <div className="flex flex-col justify-between gap-2 border-b pb-3 md:flex-row md:items-center">
        <div>
          <h2 id="open-teams-heading" className="flex items-center gap-2 text-base font-bold">
            Các nhóm đang còn chỗ trống
            <Badge variant="secondary" className="font-semibold">
              {openTeams.length} nhóm
            </Badge>
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Các nhóm đã khởi tạo nhưng chưa đủ sĩ số quy định. Nhấn "Xin gia nhập" để gửi yêu cầu
            đến Trưởng nhóm.
          </p>
        </div>
      </div>
      {openTeams.length === 0 ? (
        <EmptyState
          description="Hiện không có nhóm nào còn chỗ trống. Bạn có thể tạo nhóm mới và mời bạn học cùng tham gia."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs font-semibold text-muted-foreground">
                <th scope="col" className="px-2 py-2.5">Tên nhóm</th>
                <th scope="col" className="px-4 py-2.5">Trưởng nhóm</th>
                <th scope="col" className="px-4 py-2.5">Sĩ số</th>
                <th scope="col" className="px-4 py-2.5">Kỹ năng cần</th>
                <th scope="col" className="px-2 py-2.5 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {openTeams.map((team) => (
                <tr key={team.teamId} className="border-b last:border-b-0 hover:bg-muted/40">
                  <td className="px-2 py-3 font-medium">{team.teamName}</td>
                  <td className="px-4 py-3 text-muted-foreground">{team.leaderName}</td>
                  <td className="px-4 py-3">
                    {team.memberCount}/{team.maxMembers}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {team.neededSkills.map((skill) => (
                        <Badge key={skill} variant="outline" className="text-[11px]">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </td>
                  <td className="px-2 py-3 text-right">
                    <Button
                      size="xs"
                      variant="outline"
                      disabled
                      title="Yêu cầu gia nhập sẽ khả dụng khi backend hỗ trợ"
                    >
                      Xin gia nhập
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function UnassignedClassmatesSection({
  classmates,
}: Readonly<{
  classmates: UnassignedClassmate[];
}>) {
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return classmates;
    return classmates.filter(
      (classmate) =>
        classmate.displayName.toLowerCase().includes(needle) ||
        classmate.studentId.includes(needle) ||
        classmate.skill.toLowerCase().includes(needle),
    );
  }, [classmates, search]);

  return (
    <section className="space-y-3 pt-4" aria-labelledby="classmates-heading">
      <div className="flex flex-col justify-between gap-3 border-b pb-3 md:flex-row md:items-center">
        <div>
          <h2 id="classmates-heading" className="flex items-center gap-2 text-base font-bold">
            Sinh viên trong lớp chưa có nhóm
            <Badge variant="secondary" className="font-semibold">
              {classmates.length} sinh viên
            </Badge>
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Các sinh viên chưa tìm được nhóm đồ án. Hãy chủ động liên hệ hoặc mời bạn học cùng kỹ
            năng để thành lập nhóm mới.
          </p>
        </div>
        <div className="relative w-full md:w-64">
          <Search
            className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm theo tên, MSSV, kỹ năng..."
            className="pl-8 text-xs"
            aria-label="Tìm sinh viên chưa có nhóm"
          />
        </div>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          description={
            classmates.length === 0
              ? "Tất cả sinh viên trong lớp đã có nhóm."
              : "Không tìm thấy sinh viên phù hợp với từ khóa."
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs font-semibold text-muted-foreground">
                <th scope="col" className="px-2 py-2.5">Sinh viên</th>
                <th scope="col" className="px-4 py-2.5">MSSV</th>
                <th scope="col" className="px-4 py-2.5">Kỹ năng</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((classmate) => (
                <tr key={classmate.userId} className="border-b last:border-b-0 hover:bg-muted/40">
                  <td className="px-2 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-[10px] font-bold">
                        {initialsOf(classmate.displayName)}
                      </span>
                      <span className="font-medium">{classmate.displayName}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {classmate.studentId}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className="text-[11px]">
                      {classmate.skill}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CreateTeamDialog({
  course,
  open,
  onOpenChange,
}: Readonly<{
  course: CourseDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>) {
  const createTeam = useCreateTeam(course.courseId);
  const [teamName, setTeamName] = useState("");
  const [description, setDescription] = useState("");
  const [neededSkills, setNeededSkills] = useState("");
  const [maxMembers, setMaxMembers] = useState(String(course.teamSize.min));

  const maxMembersValue = Number(maxMembers);
  const maxMembersValid =
    Number.isInteger(maxMembersValue) &&
    maxMembersValue >= course.teamSize.min &&
    maxMembersValue <= course.teamSize.max;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (teamName.trim().length < 3 || !maxMembersValid) return;
    createTeam.mutate(
      {
        teamName: teamName.trim(),
        description: description.trim(),
        neededSkills: neededSkills.trim(),
        maxMembers: maxMembersValue,
      },
      {
        onSuccess: () => {
          toast.success("Tạo nhóm thành công. Bạn là Trưởng nhóm của nhóm mới.");
          onOpenChange(false);
        },
        onError: (error) => {
          const message =
            error instanceof ApiError ? error.message : "Không thể tạo nhóm. Vui lòng thử lại.";
          toast.error(message);
        },
      },
    );
  };

  const pending = createTeam.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tạo nhóm mới</DialogTitle>
          <DialogDescription>
            Nhóm từ {course.teamSize.min} đến {course.teamSize.max} sinh viên. Bạn sẽ trở thành
            Trưởng nhóm sau khi tạo.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="team-name">Tên nhóm</Label>
            <Input
              id="team-name"
              value={teamName}
              onChange={(event) => setTeamName(event.target.value)}
              placeholder="VD: Team NEXUS"
              required
              minLength={3}
            />
            {teamName.length > 0 && teamName.trim().length < 3 ? (
              <p className="text-xs text-destructive">Tên nhóm cần ít nhất 3 ký tự.</p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="team-description">Mô tả nhóm</Label>
            <Textarea
              id="team-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Định hướng đồ án, phong cách làm việc của nhóm..."
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="team-skills">Kỹ năng cần tuyển (phân tách bằng dấu phẩy)</Label>
            <Input
              id="team-skills"
              value={neededSkills}
              onChange={(event) => setNeededSkills(event.target.value)}
              placeholder="VD: Backend Node.js, DevOps, UI/UX"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="team-max-members">
              Sĩ số tối đa ({course.teamSize.min}–{course.teamSize.max})
            </Label>
            <Input
              id="team-max-members"
              type="number"
              value={maxMembers}
              onChange={(event) => setMaxMembers(event.target.value)}
              min={course.teamSize.min}
              max={course.teamSize.max}
              step={1}
            />
            {!maxMembersValid ? (
              <p className="text-xs text-destructive">
                Sĩ số tối đa phải từ {course.teamSize.min} đến {course.teamSize.max}.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={pending || teamName.trim().length < 3 || !maxMembersValid}
            >
              {pending ? "Đang tạo..." : "Tạo nhóm"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TeamFormationView({ course }: Readonly<{ course: CourseDetail }>) {
  const [createOpen, setCreateOpen] = useState(false);
  const deadline = course.teamFormation.registrationDeadline;
  const deadlinePassed = deadline !== null && new Date(deadline).getTime() <= Date.now();
  const permissionCtx: CoursePermissionContext = {
    membershipStatus: course.membership.status,
    role: null,
    selfCreateAllowed: course.teamFormation.selfCreateAllowed,
    formationDeadlinePassed: deadlinePassed,
  };
  const allowCreate = canCreateTeam(permissionCtx);
  const createButtonTitle = deadlinePassed
    ? "Đã quá hạn tự lập nhóm. Hãy chờ Giảng viên phân nhóm."
    : "Môn học không cho phép sinh viên tự tạo nhóm.";

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 border-b pb-4 lg:flex-row lg:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Thành lập Nhóm Đồ án</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <Users className="size-3.5 text-primary" aria-hidden />
              Giảng viên: {course.instructorName}
            </span>
            <span aria-hidden>•</span>
            <span>
              Sĩ số nhóm: <strong className="text-foreground">{course.teamSize.min}–{course.teamSize.max} sinh viên</strong>
            </span>
            <span aria-hidden>•</span>
            <span>
              Sĩ số lớp: <strong className="text-foreground">{course.classSize.total} sinh viên</strong>{" "}
              (<span className="font-medium text-emerald-700">{course.classSize.teamed} đã có nhóm</span>,{" "}
              <span className="font-semibold text-amber-700">
                {course.classSize.total - course.classSize.teamed} chưa có nhóm
              </span>
              )
            </span>
          </div>
        </div>
        {allowCreate || deadlinePassed || !course.teamFormation.selfCreateAllowed ? (
          <Button
            className="shrink-0"
            onClick={() => setCreateOpen(true)}
            disabled={!allowCreate}
            title={allowCreate ? undefined : createButtonTitle}
          >
            <UserPlus className="size-4" aria-hidden />
            Tạo nhóm mới
          </Button>
        ) : null}
      </div>

      <DeadlineBanner course={course} />

      <OpenTeamsSection openTeams={course.formation?.openTeams ?? []} />
      <UnassignedClassmatesSection
        classmates={course.formation?.unassignedClassmates ?? []}
      />

      <CreateTeamDialog course={course} open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* View: membership.status === "pending"                               */
/* ------------------------------------------------------------------ */

function PendingJoinRequestView({ course }: Readonly<{ course: CourseDetail }>) {
  const membership = course.membership;
  if (membership.status !== "pending") {
    return null;
  }
  return (
    <div className="space-y-6">
      <div className="border-b pb-4">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Clock className="size-6 text-primary" aria-hidden />
          Yêu cầu tham gia nhóm đang chờ duyệt
        </h1>
        <p className="mt-1 text-xs font-medium text-muted-foreground">
          {course.courseCode} • {course.courseName} • {course.semester}
        </p>
      </div>

      <section className="rounded-lg border bg-card p-6" aria-labelledby="pending-request-heading">
        <h2 id="pending-request-heading" className="font-semibold">
          {membership.teamName}
        </h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex flex-wrap gap-x-16 gap-y-3">
            <div>
              <dt className="text-xs text-muted-foreground">Trưởng nhóm duyệt yêu cầu</dt>
              <dd className="mt-1 inline-flex items-center gap-1.5">
                <Hourglass className="size-3.5 text-amber-600" aria-hidden />
                Đang chờ Trưởng nhóm duyệt
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Thời điểm gửi</dt>
              <dd className="mt-1">{formatDateTime(membership.requestedAt)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Trạng thái</dt>
              <dd className="mt-1">
                <Badge
                  variant="outline"
                  className="border-sky-200 bg-sky-50 text-sky-900"
                >
                  Chờ duyệt
                </Badge>
              </dd>
            </div>
          </div>
        </dl>
        <p className="mt-5 text-xs text-muted-foreground">
          Board, backlog và repository của nhóm sẽ mở sau khi Trưởng nhóm duyệt yêu cầu của bạn.
        </p>
        <Button
          className="mt-4"
          variant="outline"
          size="sm"
          disabled
          title="Chức năng hủy yêu cầu sẽ khả dụng khi backend hỗ trợ"
        >
          Hủy yêu cầu
        </Button>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* View: membership.status === "assigned" (Team Hub)                   */
/* ------------------------------------------------------------------ */

const TOPIC_STATUS: Record<
  TopicProposal["status"],
  { label: string; className: string }
> = {
  draft: { label: "CHƯA CÓ ĐỀ TÀI", className: "border-dashed bg-secondary text-muted-foreground" },
  submitted: { label: "ĐÃ NỘP (Submitted)", className: "border-sky-200 bg-sky-50 text-sky-900" },
  under_review: { label: "ĐANG CHỜ DUYỆT", className: "border-sky-200 bg-sky-50 text-sky-900" },
  revision_required: {
    label: "CẦN CHỈNH SỬA LẠI",
    className: "border-amber-200 bg-amber-50 text-amber-900",
  },
  approved: {
    label: "ĐÃ ĐƯỢC GIẢNG VIÊN PHÊ DUYỆT",
    className: "border-emerald-200 bg-emerald-50 text-emerald-800",
  },
  rejected: { label: "BỊ TỪ CHỐI", className: "border-red-200 bg-red-50 text-red-800" },
};

function TopicDraftForm({ course }: Readonly<{ course: CourseDetail }>) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  return (
    <form
      className="max-w-3xl space-y-4"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="space-y-1.5">
        <Label htmlFor="topic-title">Tên đề tài</Label>
        <Input
          id="topic-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="VD: Hệ thống Quản lý Chuỗi cung ứng Thông minh"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="topic-description">Mô tả đề tài</Label>
        <Textarea
          id="topic-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Mô tả phạm vi, công nghệ và ý tưởng chính của đồ án..."
          rows={4}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="topic-objectives">Mục tiêu (mỗi dòng một mục tiêu)</Label>
        <Textarea
          id="topic-objectives"
          value={objectives}
          onChange={(event) => setObjectives(event.target.value)}
          placeholder={"Kiến trúc Microservices gRPC.\nTích hợp IoT giám sát real-time."}
          rows={4}
        />
      </div>
      <Button
        type="submit"
        disabled
        title="Nộp đề tài sẽ khả dụng khi backend hỗ trợ API đăng ký đề tài"
      >
        <FileText className="size-4" aria-hidden />
        Soạn đề tài
      </Button>
    </form>
  );
}

function TopicTitle({
  topic,
  isDraft,
  editableByLeader,
}: Readonly<{
  topic: TopicProposal;
  isDraft: boolean;
  editableByLeader: boolean;
}>) {
  if (topic.title) {
    return <h3 className="text-lg font-bold tracking-tight">{topic.title}</h3>;
  }
  if (!isDraft) return null;
  const hint = editableByLeader
    ? "Trưởng nhóm soạn và nộp đề tài để Giảng viên phê duyệt."
    : "Trưởng nhóm sẽ soạn và nộp đề tài để Giảng viên phê duyệt.";
  return <p className="text-sm text-muted-foreground">Nhóm chưa có đề tài. {hint}</p>;
}

function TopicDetails({ topic }: Readonly<{ topic: TopicProposal }>) {
  return (
    <>
      {topic.feedback ? (
        <div className="border-l-2 border-primary py-0.5 pl-3">
          <p className="text-xs italic leading-relaxed text-muted-foreground">
            "{topic.feedback}"
          </p>
        </div>
      ) : null}

      {topic.description ? (
        <p className="text-xs leading-relaxed text-muted-foreground">{topic.description}</p>
      ) : null}

      {topic.objectives.length > 0 ? (
        <div>
          <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Mục tiêu &amp; Phạm vi triển khai chính:
          </span>
          <ul className="space-y-1.5 text-xs text-muted-foreground">
            {topic.objectives.map((objective) => (
              <li key={objective} className="flex items-start gap-2">
                <span className="mt-0.5 font-bold leading-none text-primary" aria-hidden>•</span>
                {objective}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

function ApprovedTopicAction({ projectId }: Readonly<{ projectId?: string | null }>) {
  if (!projectId) {
    return (
      <output className="text-xs text-muted-foreground">
        Đề tài đã được duyệt. Workspace của nhóm chưa sẵn sàng — vui lòng chờ giảng viên khởi
        tạo.
      </output>
    );
  }
  return (
    <Button asChild>
      <Link to={`/projects/${encodeURIComponent(projectId)}/backlog`}>
        <KanbanSquare className="size-4" aria-hidden />
        Mở Project Workspace
        <ArrowRight className="size-4" aria-hidden />
      </Link>
    </Button>
  );
}

function TopicSection({
  course,
  permissionCtx,
}: Readonly<{
  course: CourseDetail;
  permissionCtx: CoursePermissionContext;
}>) {
  const team = course.team;
  if (!team) return null;
  const topic = team.topic;
  const status = TOPIC_STATUS[topic.status];
  const isDraft = topic.status === "draft";
  const editableByLeader = canSubmitTopic(permissionCtx, isDraft ? null : topic.status);

  return (
    <section className="space-y-4 border-b pb-6" aria-labelledby="topic-heading">
      <h2 id="topic-heading" className="flex items-center gap-2 text-base font-bold">
        <FileText className="size-4 text-primary" aria-hidden />
        Đề tài đồ án
      </h2>
      <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
        <div className="max-w-3xl space-y-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <Badge variant="outline" className={cn("font-bold", status.className)}>
              <span className="text-[9px]" aria-hidden>●</span>
              {status.label}
            </Badge>
            {topic.reviewedBy && topic.reviewedAt ? (
              <span className="text-xs text-muted-foreground">
                {topic.reviewedBy} lúc {formatDateTime(topic.reviewedAt)}
              </span>
            ) : null}
          </div>

          <TopicTitle topic={topic} isDraft={isDraft} editableByLeader={editableByLeader} />
          <TopicDetails topic={topic} />
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 pt-1 lg:items-end">
          {editableByLeader && isDraft ? (
            <TopicDraftForm course={course} />
          ) : null}
          {editableByLeader && topic.status === "revision_required" ? (
            <Button
              disabled
              title="Chỉnh sửa lại đề tài sẽ khả dụng khi backend hỗ trợ API cập nhật đề tài"
            >
              Chỉnh sửa lại
            </Button>
          ) : null}
          {topic.status === "approved" ? (
            <ApprovedTopicAction projectId={team.projectId} />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function MembersSection({ teamName, members }: Readonly<{ teamName: string; members: TeamMember[] }>) {
  return (
    <section className="space-y-3" aria-labelledby="members-heading">
      <div className="flex items-center justify-between pb-1">
        <div>
          <h2 id="members-heading" className="text-base font-bold">
            Thành viên {teamName}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {members.length} sinh viên • Trưởng nhóm phụ trách liên lạc giảng viên
          </p>
        </div>
        <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          Danh sách đã khóa
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <th scope="col" className="px-2 py-3">Thành viên</th>
              <th scope="col" className="px-4 py-3">MSSV</th>
              <th scope="col" className="px-4 py-3">Email trường</th>
              <th scope="col" className="px-4 py-3">Vai trò chuyên môn</th>
              <th scope="col" className="px-4 py-3">Trách nhiệm trong đồ án</th>
              <th scope="col" className="px-2 py-3 text-right">Vai trò</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.userId} className="border-b last:border-b-0 hover:bg-muted/40">
                <td className="px-2 py-3.5">
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                        member.role === "leader"
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-foreground",
                      )}
                      aria-hidden
                    >
                      {initialsOf(member.displayName)}
                    </span>
                    <span className="font-bold">{member.displayName}</span>
                  </div>
                </td>
                <td className="px-4 py-3.5 font-mono font-medium">{member.studentId}</td>
                <td className="px-4 py-3.5 text-muted-foreground">{member.email}</td>
                <td className="px-4 py-3.5">
                  <span className="inline-block rounded bg-muted px-2 py-0.5 font-medium">
                    {member.skill}
                  </span>
                </td>
                <td className="px-4 py-3.5 text-muted-foreground">{member.responsibility}</td>
                <td className="px-2 py-3.5 text-right">
                  {member.role === "leader" ? (
                    <Badge className="text-[10px] font-bold">TRƯỞNG NHÓM</Badge>
                  ) : (
                    <Badge variant="secondary" className="text-[10px] font-semibold">Thành viên</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RepositoryCard({ repository }: Readonly<{ repository: string }>) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-1.5 flex items-center justify-between text-xs text-muted-foreground">
        <span className="text-[10px] font-semibold uppercase tracking-wider">
          Kho lưu trữ (Repository)
        </span>
        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600">
          <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
          Webhook active
        </span>
      </div>
      <a
        className="block truncate font-mono text-xs font-semibold text-primary hover:underline"
        href={`https://github.com/${repository}`}
        target="_blank"
        rel="noreferrer"
      >
        {repository}
      </a>
      <p className="mt-1 text-[11px] text-muted-foreground">
        <GitBranch className="mr-1 inline size-3" aria-hidden />
        Nhánh chính: <code className="font-mono font-medium">main</code> • Đồng bộ commit tự động
      </p>
    </div>
  );
}

function TeamHubView({ course }: Readonly<{ course: CourseDetail }>) {
  const team = course.team;
  if (!team) {
    return (
      <EmptyState
        title="Chưa tải được dữ liệu nhóm"
        description="Bạn đã được ghi nhận trong một nhóm nhưng dữ liệu nhóm hiện chưa sẵn sàng. Vui lòng tải lại trang."
      />
    );
  }
  const role = course.membership.status === "assigned" ? course.membership.role : null;
  const permissionCtx: CoursePermissionContext = {
    membershipStatus: course.membership.status,
    role,
    selfCreateAllowed: false,
    formationDeadlinePassed: false,
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2 border-b pb-5">
        <div className="flex items-center gap-2.5">
          <Badge className="tracking-wide">{course.courseCode}</Badge>
          <h1 className="text-2xl font-bold tracking-tight">
            Nhóm Đồ án &amp; Đăng ký Đề tài
          </h1>
        </div>
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>
            Môn học:{" "}
            <strong className="font-semibold text-foreground">
              {course.courseName}
            </strong>
          </span>
          <span aria-hidden>•</span>
          <span>
            Giảng viên hướng dẫn:{" "}
            <strong className="font-semibold text-foreground">{course.instructorName}</strong>
          </span>
          <span aria-hidden>•</span>
          <span>
            Học kỳ:{" "}
            <strong className="font-semibold text-foreground">{course.semester}</strong>
          </span>
          <span aria-hidden>•</span>
          <span className="inline-flex items-center gap-1">
            <Users className="size-3.5" aria-hidden />
            <strong className="font-semibold text-foreground">{team.teamName}</strong>
            ({team.memberCount}/{team.maxMembers} thành viên)
          </span>
        </p>
      </div>

      <TopicSection course={course} permissionCtx={permissionCtx} />
      <MembersSection teamName={team.teamName} members={team.members} />

      {team.repository ? (
        <section className="pt-2">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <RepositoryCard repository={team.repository} />
          </div>
        </section>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Route component                                                     */
/* ------------------------------------------------------------------ */

export function Component() {
  const { courseId } = useParams();
  const courseQuery = useCourseDetail(courseId ?? "");

  if (courseQuery.isPending) {
    return <PageSkeleton label="Đang tải thông tin môn học" />;
  }

  if (courseQuery.isError) {
    const apiError =
      courseQuery.error instanceof ApiError ? courseQuery.error : null;
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-4 pt-7 sm:px-6 lg:px-8">
        {apiError?.status === 404 ? (
          <EmptyState
            title="Không tìm thấy môn học"
            description="Môn học này không tồn tại hoặc bạn chưa được đăng ký. Hãy kiểm tra lại đường dẫn hoặc quay lại danh sách môn học."
            action={
              <Button asChild variant="outline" size="sm">
                <Link to="/courses">Về Môn học của tôi</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState
            error={courseQuery.error}
            onRetry={() => void courseQuery.refetch()}
          />
        )}
      </div>
    );
  }

  const course = courseQuery.data;
  if (!course || !courseId) {
    return (
      <div className="mx-auto max-w-6xl px-4 pt-7 sm:px-6 lg:px-8">
        <EmptyState
          title="Không tìm thấy môn học"
          description="Không tải được thông tin môn học."
          action={
            <Button asChild variant="outline" size="sm">
              <Link to="/courses">Về Môn học của tôi</Link>
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pt-7 sm:px-6 lg:px-8">
      <Breadcrumbs
        items={[
          { label: "Môn học của tôi", to: "/courses" },
          { label: `${course.courseCode} — ${course.courseName}` },
        ]}
      />
      {course.membership.status === "none" ? (
        <TeamFormationView course={course} />
      ) : course.membership.status === "pending" ? (
        <PendingJoinRequestView course={course} />
      ) : (
        <TeamHubView course={course} />
      )}
      <footer className="flex items-center justify-center border-t pt-6 pb-6 text-xs text-muted-foreground">
        <CheckCircle2 className="mr-1.5 size-3.5" aria-hidden />
        UTask Academic Portal • Quản lý đồ án &amp; Nghiên cứu khoa học sinh viên
      </footer>
    </div>
  );
}

export default Component;