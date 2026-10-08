import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import { StatCard, activityText } from "@/features/teacher/components/shared";
import { useTeacherTeams } from "@/lib/query/teacherFlowHooks";

export function Component() {
  const course = useTeacherCourseContext();
  const teams = useTeacherTeams(course.courseId);

  if (course.studentCount === 0 && course.teamCount === 0) {
    return (
      <EmptyState
        title="Lớp chưa có sinh viên"
        description="Lớp mới chưa có sinh viên hay nhóm là trạng thái hợp lệ. Việc thêm sinh viên sẽ khả dụng ở giai đoạn sau."
      />
    );
  }

  const withoutProject = teams.data?.teams.filter((team) => team.project === null) ?? [];
  const base = `/teacher/courses/${course.courseId}`;

  return (
    <div className="space-y-6">
      <section aria-label="Chỉ số của lớp" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Sinh viên" value={course.studentCount} />
        <StatCard label="Chưa có nhóm" value={course.studentsWithoutTeam} />
        <StatCard label="Nhóm" value={course.teamCount} />
        <StatCard
          label="Nhóm có tín hiệu cần chú ý"
          value={course.teamsWithSignals}
          tone={course.teamsWithSignals > 0 ? "attention" : "default"}
          hint="Xem nguyên nhân ở mục Giám sát"
        />
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-base">Quy định nhóm và tham gia lớp</CardTitle>
          <Badge variant="secondary">Chỉ xem</Badge>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Sĩ số nhóm
              </dt>
              <dd className="mt-1 text-lg font-semibold">
                {course.teamSize.min}–{course.teamSize.max}{" "}
                <span className="text-sm font-normal text-muted-foreground">thành viên / nhóm</span>
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Mã tham gia lớp
              </dt>
              <dd className="mt-1 text-lg font-semibold">
                {course.joinCode ? (
                  <span className="font-mono">{course.joinCode}</span>
                ) : (
                  <span className="text-base font-normal text-muted-foreground">Chưa có mã</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Giảng viên phụ trách
              </dt>
              <dd className="mt-1">{course.instructors.map((entry) => entry.name).join(", ")}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Hoạt động gần nhất
              </dt>
              <dd className="mt-1">{activityText(course.lastActivity)}</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">
            Chỉnh sửa quy định, hạn lập nhóm và trạng thái nhận sinh viên sẽ khả dụng ở giai đoạn
            sau.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nhóm chưa có project</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {teams.isPending ? (
              <p className="text-muted-foreground" role="status">Đang tải…</p>
            ) : teams.isError ? (
              <p className="text-muted-foreground">Không tải được danh sách nhóm.</p>
            ) : withoutProject.length === 0 ? (
              <p className="text-muted-foreground">Mọi nhóm trong lớp đều đã có project.</p>
            ) : (
              <ul className="space-y-1">
                {withoutProject.map((team) => (
                  <li key={team.teamId} className="flex items-center justify-between gap-2">
                    <span className="font-medium">{team.name}</span>
                    <Badge variant="outline">{team.memberCount} thành viên</Badge>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              Xem workspace của nhóm (Backlog, Board, Code) sẽ khả dụng ở giai đoạn sau.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Đi nhanh</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`${base}/students`}>Danh sách sinh viên</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${base}/teams`}>Cơ cấu nhóm</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to={`${base}/oversight`}>Giám sát tiến độ</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
