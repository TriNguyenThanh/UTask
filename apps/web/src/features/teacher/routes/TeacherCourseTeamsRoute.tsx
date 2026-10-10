import { Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { TeamAdjustDialog } from "@/features/teacher/components/TeamAdjustDialog";
import {
  PersonAvatar,
  ProgressMeter,
  StatCard,
  TeacherQueryError,
  activityText,
} from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import type { TeacherTeam } from "@/lib/api/teacherFlow";
import { useTeacherStudents, useTeacherTeams } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

type TeamFilter = "all" | "open-slots" | "no-project";

function parseFilter(value: string | null): TeamFilter {
  return value === "open-slots" || value === "no-project" ? value : "all";
}

function TeamCard({ team, courseId }: Readonly<{ team: TeacherTeam; courseId: string }>) {
  const openSlots = Math.max(team.maxMembers - team.memberCount, 0);
  return (
    <Card className="flex flex-col gap-4 py-5">
      <CardHeader className="gap-1 pb-0">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-base">{team.name}</CardTitle>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge
              variant="outline"
              className={cn(openSlots > 0 && "border-amber-300 bg-amber-50 text-amber-900")}
            >
              {team.memberCount}/{team.maxMembers} thành viên
              {openSlots > 0 ? ` • còn ${openSlots} chỗ` : ""}
            </Badge>
            {team.project ? (
              <Badge variant="secondary">{team.project.key}</Badge>
            ) : (
              <Badge variant="outline">Chưa có project</Badge>
            )}
          </div>
        </div>
        {team.project ? <p className="text-sm font-medium">{team.project.name}</p> : null}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 text-sm">
        <div>
          <p className="sr-only">
            Trưởng nhóm:{" "}
            {team.leaders.length > 0
              ? team.leaders.map((leader) => leader.name).join(", ")
              : "Chưa có"}
          </p>
          <ul aria-label={`Thành viên ${team.name}`} className="grid gap-2 sm:grid-cols-2">
            {team.members.map((member) => (
              <li
                key={member.userId}
                className="flex items-center gap-2.5 rounded-md border bg-background p-2"
              >
                <PersonAvatar name={member.name} />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-1.5 font-medium">
                    {member.name}
                    {member.role === "leader" ? (
                      <Badge variant="secondary" className="text-[10px]">
                        Leader
                      </Badge>
                    ) : null}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    MSSV: {member.studentCode}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <ProgressMeter
          label={`Tiến độ ${team.name}`}
          progress={team.progress}
          emptyText={
            team.project ? "Chưa có dữ liệu tiến độ" : "Chưa có project để đo tiến độ"
          }
        />
        <p className="text-xs text-muted-foreground">{activityText(team.lastActivity)}</p>
        <div className="mt-auto pt-1">
          <Button asChild variant="outline" className="w-full">
            <Link to={`/teacher/courses/${courseId}/teams/${team.teamId}`}>
              Xem chi tiết {team.name}
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function UnassignedPanel({ courseId }: Readonly<{ courseId: string }>) {
  const students = useTeacherStudents(courseId);
  if (students.isPending) return <PageSkeleton label="Đang tải danh sách sinh viên" />;
  if (students.isError) {
    return <TeacherQueryError error={students.error} onRetry={() => void students.refetch()} />;
  }
  const unassigned = students.data.students.filter((student) => student.team === null);
  return (
    <section aria-label="Sinh viên chưa có nhóm" className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">Sinh viên chưa có nhóm</h2>
        <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-900">
          {unassigned.length} sinh viên
        </Badge>
      </div>
      {unassigned.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {students.data.students.length === 0
            ? "Lớp chưa có sinh viên."
            : "Mọi sinh viên đã có nhóm trong lớp này."}
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {unassigned.map((student) => (
            <li
              key={student.userId}
              className="flex items-center gap-2.5 rounded-md border bg-background p-2 text-sm"
            >
              <PersonAvatar name={student.name} />
              <span className="min-w-0">
                <span className="block font-medium">{student.name}</span>
                <span className="block text-xs text-muted-foreground">
                  {student.studentCode}
                  {student.pendingTeam ? ` • Chờ duyệt vào ${student.pendingTeam.name}` : ""}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TeamsPanel({ courseId }: Readonly<{ courseId: string }>) {
  const teams = useTeacherTeams(courseId);
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const filter = parseFilter(searchParams.get("filter"));

  function setParam(key: string, value: string, empty: string) {
    const params = new URLSearchParams(searchParams);
    if (value === empty) params.delete(key);
    else params.set(key, value);
    setSearchParams(params);
  }

  if (teams.isPending) return <PageSkeleton label="Đang tải danh sách nhóm" />;
  if (teams.isError) {
    return <TeacherQueryError error={teams.error} onRetry={() => void teams.refetch()} />;
  }
  const all = teams.data.teams;
  if (all.length === 0) {
    return (
      <EmptyState
        title="Lớp chưa có nhóm"
        description="Nhóm sẽ xuất hiện tại đây khi sinh viên hoặc giảng viên tạo nhóm."
      />
    );
  }

  const needle = query.trim().toLowerCase();
  const visible = all.filter((team) => {
    if (filter === "open-slots" && team.memberCount >= team.maxMembers) return false;
    if (filter === "no-project" && team.project !== null) return false;
    if (!needle) return true;
    return [team.name, team.project?.name ?? "", ...team.members.map((member) => member.name)].some(
      (value) => value.toLowerCase().includes(needle),
    );
  });

  const chips: { id: TeamFilter; label: string; count: number }[] = [
    { id: "all", label: "Tất cả nhóm", count: all.length },
    {
      id: "open-slots",
      label: "Còn chỗ trống",
      count: all.filter((team) => team.memberCount < team.maxMembers).length,
    },
    {
      id: "no-project",
      label: "Chưa có project",
      count: all.filter((team) => team.project === null).length,
    },
  ];

  return (
    <section aria-label="Danh sách nhóm" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex w-full flex-col gap-1 sm:w-80">
          <label htmlFor="teacher-team-search" className="text-xs font-medium text-muted-foreground">
            Tìm nhóm
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="teacher-team-search"
              type="search"
              className="pl-9"
              placeholder="Tên nhóm, project hoặc thành viên"
              value={query}
              onChange={(event) => setParam("q", event.target.value, "")}
            />
          </div>
        </div>
        <TeamAdjustDialog />
      </div>

      <fieldset aria-label="Lọc nhóm" className="m-0 flex min-w-0 flex-wrap gap-1.5 border-0 p-0">
        {chips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            aria-pressed={filter === chip.id}
            onClick={() => setParam("filter", chip.id, "all")}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
              filter === chip.id
                ? "border-primary bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-secondary",
            )}
          >
            {chip.label} ({chip.count})
          </button>
        ))}
      </fieldset>

      {visible.length === 0 ? (
        <EmptyState
          title="Không có nhóm khớp bộ lọc"
          description="Thử đổi từ khóa hoặc bộ lọc."
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {visible.map((team) => (
            <TeamCard key={team.teamId} team={team} courseId={courseId} />
          ))}
        </div>
      )}
    </section>
  );
}

export function Component() {
  const course = useTeacherCourseContext();
  const grouped = course.studentCount - course.studentsWithoutTeam;

  return (
    <div className="space-y-6">
      <section aria-label="Chỉ số nhóm" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Tổng số sinh viên" value={course.studentCount} />
        <StatCard label="Đã có nhóm" value={grouped} />
        <StatCard
          label="Chưa có nhóm"
          value={course.studentsWithoutTeam}
          tone={course.studentsWithoutTeam > 0 ? "attention" : "default"}
        />
        <StatCard
          label="Quy định sĩ số"
          value={`${course.teamSize.min}–${course.teamSize.max}`}
          hint="Thành viên mỗi nhóm"
        />
      </section>

      <UnassignedPanel courseId={course.courseId} />
      <TeamsPanel courseId={course.courseId} />

      <p className="text-xs text-muted-foreground">
        Điều chỉnh nhóm hiện chỉ kiểm tra và xem trước; việc áp dụng sẽ khả dụng khi có hợp đồng API
        và chính sách về sĩ số, Leader thay thế và quyền xem lịch sử.
      </p>
    </div>
  );
}
