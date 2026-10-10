import { AlertTriangle, CheckCircle2, Clock3, FolderGit2, GitBranch, Users } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";
import type {
  TeacherActivity,
  TeacherCourseSummary,
  TeacherSignal,
  TeacherSignalCategory,
  TeacherTeamProgress,
} from "@/lib/api/teacherFlow";
import { cn } from "@/lib/utils";

/** "SE330 • Lớp 2" — the code alone is not unique across classes. */
export function courseLabel(course: Pick<TeacherCourseSummary, "courseCode" | "section">): string {
  return course.section ? `${course.courseCode} • ${course.section}` : course.courseCode;
}

const ACTIVITY_LABELS: Record<TeacherActivity["kind"], string> = {
  "issue-updated": "Cập nhật issue",
};

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Always names the kind of activity; an absent value is stated, never shown as "now". */
export function activityText(activity: TeacherActivity | null): string {
  return activity
    ? `${ACTIVITY_LABELS[activity.kind]} • ${formatDateTime(activity.at)}`
    : "Chưa ghi nhận hoạt động";
}

/**
 * Not found and not allowed are one state on purpose: the server answers
 * both the same way so the UI cannot reveal which classes exist.
 */
export function isCourseUnavailable(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.status === 404);
}

export function CourseUnavailable() {
  return (
    <EmptyState
      title="Không tìm thấy lớp học"
      description="Lớp học không tồn tại hoặc bạn không phụ trách lớp này."
      action={
        <Button asChild variant="outline" size="sm">
          <Link to="/teacher/courses">Về danh sách lớp phụ trách</Link>
        </Button>
      }
    />
  );
}

/** Error body for a Teacher query: unavailable class vs. a retryable failure. */
export function TeacherQueryError({ error, onRetry }: Readonly<{ error: unknown; onRetry: () => void }>) {
  if (isCourseUnavailable(error)) {
    return <CourseUnavailable />;
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: Readonly<{
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "attention";
}>) {
  return (
    <fieldset
      aria-label={label}
      className="m-0 flex min-w-0 flex-col gap-1 rounded-xl border bg-card px-0 py-4 text-card-foreground shadow-sm"
    >
      <CardHeader className="pb-1">
        <CardTitle className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className={cn("text-3xl font-bold", tone === "attention" && "text-amber-700")}>
          {value}
        </div>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </fieldset>
  );
}

function initialsOf(name: string): string {
  const parts = name
    .replace(/^(TS|ThS|PGS|GS)\.\s*/u, "")
    .trim()
    .split(/\s+/u);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "";
  return (first + last).toUpperCase();
}

/** Decorative initials; the name is always printed next to it. */
export function PersonAvatar({ name, className }: Readonly<{ name: string; className?: string }>) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-xs font-semibold text-accent-foreground",
        className,
      )}
    >
      {initialsOf(name)}
    </span>
  );
}

const BASIS_TEXT: Record<TeacherTeamProgress["basis"], string> = {
  "sprint-points": "theo điểm Sprint đang chạy",
  issues: "theo số issue đã hoàn thành",
};

/** Progress with its basis spelled out; unknown is stated, never drawn as 0%. */
export function ProgressMeter({
  label,
  progress,
  emptyText,
}: Readonly<{
  label: string;
  progress: TeacherTeamProgress | null;
  emptyText: string;
}>) {
  if (!progress) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }
  return (
    <div className="space-y-1">
      <div className="flex justify-between gap-2 text-sm">
        <span className="text-muted-foreground">Tiến độ ({BASIS_TEXT[progress.basis]})</span>
        <span className="font-semibold">{progress.percent}%</span>
      </div>
      <progress
        aria-label={label}
        max={100}
        value={progress.percent}
        className="h-2 w-full appearance-none overflow-hidden rounded-full bg-secondary [&::-moz-progress-bar]:bg-primary [&::-webkit-progress-bar]:bg-secondary [&::-webkit-progress-value]:rounded-full [&::-webkit-progress-value]:bg-primary"
      />
    </div>
  );
}

const CATEGORY_LABELS: Record<TeacherSignalCategory, string> = {
  "no-data": "Thiếu dữ liệu",
  "stale-data": "Dữ liệu cũ",
  connection: "Kết nối GitHub",
  unmapped: "Chưa ánh xạ",
  structure: "Cơ cấu nhóm",
};

/**
 * Signals always carry their cause as text, what kind of problem it is, when
 * the evidence is from (or that there is no time) and where the data can be
 * checked. Colour is only reinforcement. "Missing", "old", "disconnected" and
 * "not mapped" are different labels on purpose: none of them says anything
 * about a student, and none becomes a score.
 */
export function SignalList({
  signals,
  emptyText,
  subject,
}: Readonly<{
  signals: TeacherSignal[];
  emptyText?: string;
  /** Whose signals these are (a team name). Makes each source link's accessible name unique. */
  subject?: string;
}>) {
  if (signals.length === 0) {
    return emptyText ? (
      <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <CheckCircle2 className="size-4 text-emerald-600" aria-hidden />
        {emptyText}
      </p>
    ) : null;
  }
  return (
    <ul className="space-y-1.5">
      {signals.map((signal) => (
        <li
          key={signal.code}
          className="space-y-1 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-950"
        >
          <p className="flex items-start gap-1.5 font-medium">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              <span className="mr-1.5 rounded border border-amber-300 bg-white/70 px-1 py-px text-[10px] font-semibold uppercase tracking-wide">
                {CATEGORY_LABELS[signal.category]}
              </span>
              {signal.label}
            </span>
          </p>
          <p className="pl-5 text-[11px] text-amber-900/80">
            {signal.at ? `Bằng chứng lúc ${formatDateTime(signal.at)}` : "Nguồn không cho biết thời điểm"}
            {signal.source ? (
              <>
                {" • "}
                <Link
                  to={signal.source.path}
                  aria-label={subject ? `${signal.source.label} (${subject})` : undefined}
                  className="font-semibold underline"
                >
                  {signal.source.label}
                </Link>
              </>
            ) : null}
          </p>
        </li>
      ))}
    </ul>
  );
}

/** Metric with no source yet: stated plainly instead of a made-up zero. */
export function NoData() {
  return <span className="text-base font-semibold text-muted-foreground">Chưa có dữ liệu</span>;
}

/**
 * A control for a later phase: really disabled, with the reason both as a
 * tooltip and as text a screen reader announces.
 */
export function DisabledAction({
  children,
  reason,
  variant = "outline",
  className,
}: Readonly<{
  children: ReactNode;
  reason: string;
  variant?: "default" | "outline";
  className?: string;
}>) {
  const reasonId = useId();
  return (
    <>
      <Button
        type="button"
        variant={variant}
        disabled
        title={reason}
        aria-describedby={reasonId}
        className={className}
      >
        {children}
      </Button>
      <span id={reasonId} className="sr-only">
        {reason}
      </span>
    </>
  );
}

function CourseSignalSummary({ course }: Readonly<{ course: TeacherCourseSummary }>) {
  if (course.teamCount === 0) {
    return <p className="text-xs text-muted-foreground">Lớp chưa có nhóm nào để theo dõi.</p>;
  }
  if (course.teamsWithSignals > 0) {
    return (
      <Badge variant="outline" className="w-fit border-amber-300 bg-amber-50 text-amber-900">
        <AlertTriangle aria-hidden /> {course.teamsWithSignals} nhóm có tín hiệu cần chú ý
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="w-fit border-emerald-300 bg-emerald-50 text-emerald-900">
      <CheckCircle2 aria-hidden /> Chưa phát hiện tín hiệu cần chú ý
    </Badge>
  );
}

export function CourseCard({ course }: Readonly<{ course: TeacherCourseSummary }>) {
  const base = `/teacher/courses/${course.courseId}`;
  return (
    <Card className="flex flex-col gap-4 py-5">
      <CardHeader className="gap-3 pb-0">
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="flex h-10 min-w-14 shrink-0 items-center justify-center rounded-md border bg-primary-subtle px-2 text-xs font-bold text-accent-foreground"
          >
            {course.courseCode}
          </span>
          <div className="min-w-0 flex-1">
            <CardTitle className="text-base leading-snug">
              <Link to={base} className="hover:underline focus-visible:underline">
                {course.name}
              </Link>
            </CardTitle>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {courseLabel(course)} • {course.term}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 text-sm">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
          <div>
            <dt className="flex items-center gap-1 text-xs text-muted-foreground">
              <Users className="size-3.5" aria-hidden /> Sinh viên
            </dt>
            <dd className="font-semibold">{course.studentCount}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Chưa có nhóm</dt>
            <dd className="font-semibold">{course.studentsWithoutTeam}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1 text-xs text-muted-foreground">
              <GitBranch className="size-3.5" aria-hidden /> Nhóm
            </dt>
            <dd className="font-semibold">{course.teamCount}</dd>
          </div>
          <div>
            <dt className="flex items-center gap-1 text-xs text-muted-foreground">
              <FolderGit2 className="size-3.5" aria-hidden /> Nhóm chưa có project
            </dt>
            <dd className="font-semibold">{course.teamsWithoutProject}</dd>
          </div>
        </dl>

        <CourseSignalSummary course={course} />

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock3 className="size-3.5" aria-hidden />
            {activityText(course.lastActivity)}
          </p>
          <nav
            aria-label={`Lối tắt của ${courseLabel(course)}`}
            className="flex flex-wrap gap-1.5"
          >
            <Button asChild size="sm" variant="outline">
              <Link to={`${base}/students`}>Sinh viên</Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to={`${base}/teams`}>Nhóm</Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to={`${base}/oversight`}>Giám sát</Link>
            </Button>
          </nav>
        </div>
      </CardContent>
    </Card>
  );
}
