import { Link, useParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FeedbackComposer } from "@/features/teacher/components/FeedbackComposer";
import {
  PersonAvatar,
  ProgressMeter,
  SignalList,
  TeacherQueryError,
  activityText,
  formatDate,
} from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import type { CodeSyncState } from "@/features/projects/types";
import { ApiError } from "@/lib/api/errors";
import type { TeacherIssueStatus, TeacherTeamDetail } from "@/lib/api/teacherFlow";
import { useProjectCode } from "@/lib/query/studentFlowHooks";
import { useTeacherTeam } from "@/lib/query/teacherFlowHooks";

const STATUS_LABELS: Record<TeacherIssueStatus, string> = {
  todo: "Cần làm",
  "in-progress": "Đang làm",
  review: "Chờ review",
  done: "Hoàn thành",
};

const SYNC_LABELS: Record<CodeSyncState, string> = {
  synced: "Đã đồng bộ",
  "pending-webhook": "Đang chờ webhook đồng bộ",
  "webhook-error": "Webhook đồng bộ gặp lỗi, dữ liệu có thể không mới nhất",
  "token-expired": "Token GitHub của nhóm đã hết hạn",
  "no-repo-permission": "UTask chưa có quyền đọc repository",
  disconnected: "Nhóm chưa kết nối GitHub",
  "no-repository": "Dự án chưa có repository",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Fact({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
}

/**
 * GitHub block. It loads on its own: a failure here is shown here and never
 * hides the task data next to it. "No repository" and "project missing" are
 * different states: the second never reaches this component.
 */
function GitHubSection({ projectId }: Readonly<{ projectId: string }>) {
  const code = useProjectCode(projectId);

  let body: React.ReactNode;
  if (code.isPending) {
    body = (
      <output aria-label="Đang tải dữ liệu GitHub" className="block space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </output>
    );
  } else if (code.isError) {
    body = <ErrorState error={code.error} onRetry={() => void code.refetch()} />;
  } else {
    const data = code.data;
    body = (
      <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <Fact label="Trạng thái đồng bộ">{SYNC_LABELS[data.syncState]}</Fact>
        <Fact label="Repository">
          {data.repository ? (
            <span className="font-mono">{data.repository}</span>
          ) : (
            <span className="text-muted-foreground">Chưa có</span>
          )}
        </Fact>
        {data.repository ? (
          <>
            <Fact label="Commit gần nhất">
              {data.latestCommitSha ? (
                <span className="font-mono">{data.latestCommitSha}</span>
              ) : (
                <span className="text-muted-foreground">Chưa có dữ liệu</span>
              )}
            </Fact>
            <Fact label="Số commit / PR">
              {data.stats.commits} commit • {data.stats.pullRequests.open} PR mở •{" "}
              {data.stats.pullRequests.merged} PR đã merge
            </Fact>
          </>
        ) : null}
        <Fact label="Thời điểm đồng bộ gần nhất">
          <span className="text-muted-foreground">Chưa có dữ liệu</span>
        </Fact>
      </dl>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">GitHub</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {body}
        {code.isSuccess && code.data.repository ? (
          <Button asChild variant="outline" size="sm">
            <Link to={`/projects/${projectId}/code`}>Xem chi tiết mã nguồn</Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/**
 * Feedback to the team. Reading history needs a source that does not exist
 * yet, so it says so; writing is a draft only. Nothing here changes tasks,
 * deadlines or assignees.
 */
function FeedbackSection({ detail }: Readonly<{ detail: TeacherTeamDetail }>) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Phản hồi cho nhóm</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Lịch sử phản hồi</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Chưa có phản hồi nào để hiển thị: chưa có API phản hồi nên lịch sử chưa có nguồn dữ liệu.
          </p>
        </div>
        <FeedbackComposer
          scope={`team.${detail.team.courseId}.${detail.team.teamId}`}
          label="Soạn phản hồi cho nhóm (nháp)"
        />
      </CardContent>
    </Card>
  );
}

function TeamBody({ detail }: Readonly<{ detail: TeacherTeamDetail }>) {
  const { project } = detail;
  const overdue = detail.overdue;

  return (
    <div className="space-y-6">
      {detail.signals.length > 0 ? (
        <section aria-label="Tín hiệu cần chú ý" className="space-y-2">
          <h2 className="text-sm font-semibold">Tín hiệu cần chú ý</h2>
          <SignalList signals={detail.signals} subject={detail.team.name} />
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Thành viên ({detail.members.length}/{detail.maxMembers})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {detail.members.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nhóm chưa có thành viên.</p>
            ) : (
              <ul aria-label={`Thành viên ${detail.team.name}`} className="space-y-2">
                {detail.members.map((member) => (
                  <li
                    key={member.userId}
                    className="flex items-center gap-2.5 rounded-md border bg-background p-2"
                  >
                    <PersonAvatar name={member.name} />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium">{member.name}</span>
                      <span className="block text-xs text-muted-foreground">
                        MSSV: {member.studentCode}
                      </span>
                    </span>
                    <Badge variant={member.role === "leader" ? "default" : "outline"}>
                      {member.role === "leader" ? "Leader" : "Thành viên"}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              Đóng góp của từng thành viên không được xếp hạng hay quy ra điểm ở đây.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Project và tiến độ</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {project ? (
              <>
                <p className="text-sm">
                  <span className="font-semibold">{project.name}</span>{" "}
                  <Badge variant="secondary">{project.key}</Badge>
                </p>
                <ProgressMeter
                  label={`Tiến độ ${detail.team.name}`}
                  progress={detail.progress}
                  emptyText="Chưa có dữ liệu tiến độ"
                />
                {detail.sprint ? (
                  <p className="text-xs text-muted-foreground">
                    {detail.sprint.name} • {detail.sprint.completedPoints}/{detail.sprint.totalPoints}{" "}
                    điểm • kết thúc {formatDate(detail.sprint.endsAt)}
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Không có Sprint đang chạy.</p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nhóm chưa có project nên chưa có tiến độ, issue hay GitHub để xem.
              </p>
            )}
            <p className="text-xs text-muted-foreground">{activityText(detail.lastActivity)}</p>
          </CardContent>
        </Card>
      </div>

      {project ? null : <FeedbackSection detail={detail} />}

      {project ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Issue theo trạng thái</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {detail.issues ? (
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {(Object.keys(STATUS_LABELS) as TeacherIssueStatus[]).map((status) => (
                    <div key={status} className="rounded-md border bg-background p-3">
                      <dt className="text-xs text-muted-foreground">{STATUS_LABELS[status]}</dt>
                      <dd className="text-2xl font-bold">{detail.issues!.byStatus[status]}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">Project chưa có issue nào.</p>
              )}
              <div className="text-sm" aria-label="Issue quá hạn">
                <span className="font-semibold">Quá hạn: </span>
                {overdue ? (
                  <>
                    {overdue.overdue}/{overdue.withDueDate} issue có hạn chót{" "}
                    <span className="text-xs text-muted-foreground">
                      (chưa hoàn thành và hạn chót trước {formatDateTime(detail.asOf)})
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground">
                    Chưa có dữ liệu (không issue nào có hạn chót)
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          <GitHubSection projectId={project.projectId} />

          <FeedbackSection detail={detail} />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Xem workspace của nhóm</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link to={`/projects/${project.projectId}/backlog`}>Backlog</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/projects/${project.projectId}/board`}>Bảng công việc</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/projects/${project.projectId}/code`}>Mã nguồn</Link>
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Workspace mở ở chế độ chỉ xem: bạn không tạo, sửa hay gán task, không quản lý Sprint
                và không có cài đặt dự án.
              </p>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

export function Component() {
  const { teamId = "" } = useParams();
  const course = useTeacherCourseContext();
  const team = useTeacherTeam(course.courseId, teamId);

  if (team.isPending) {
    return <PageSkeleton label="Đang tải thông tin nhóm" />;
  }
  if (team.isError) {
    // The class itself loaded (the layout is above), so a 404 here is the team.
    if (team.error instanceof ApiError && team.error.status === 404) {
      return (
        <EmptyState
          title="Không tìm thấy nhóm"
          description="Nhóm không tồn tại hoặc không thuộc lớp này."
          action={
            <Button asChild variant="outline" size="sm">
              <Link to={`/teacher/courses/${course.courseId}/teams`}>Về danh sách nhóm</Link>
            </Button>
          }
        />
      );
    }
    return <TeacherQueryError error={team.error} onRetry={() => void team.refetch()} />;
  }

  const detail = team.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-bold tracking-tight">{detail.team.name}</h2>
          <p className="text-sm text-muted-foreground">
            {detail.project ? detail.project.name : "Chưa có project"}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/teacher/courses/${course.courseId}/teams`}>Về danh sách nhóm</Link>
        </Button>
      </div>
      <TeamBody detail={detail} />
    </div>
  );
}
