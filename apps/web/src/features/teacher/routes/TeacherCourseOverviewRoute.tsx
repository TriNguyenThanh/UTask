import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TeacherCourseDetail } from "@/lib/api/teacherFlow";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import { ActivityList } from "@/features/teacher/components/ActivityList";
import { NoData, StatCard, activityText } from "@/features/teacher/components/shared";
import { useTeacherTeams } from "@/lib/query/teacherFlowHooks";

/** Mã thô của Classroom không đọc lại được; chỉ biết mã còn hạn hay không. */
function joinCodeText(course: TeacherCourseDetail): string {
  const expires = course.classroom?.joinCodeExpiresAt;
  if (!course.classroom) return "Chưa có mã";
  return expires && new Date(expires).getTime() > Date.now() ? "Đang bật" : "Chưa có mã";
}

export function Component() {
  const course = useTeacherCourseContext();
  const teams = useTeacherTeams(course.courseId);

  if (course.studentCount === 0 && course.teamCount === 0) {
    return (
      <EmptyState
        title="Lớp chưa có sinh viên"
        description={
          course.classroom
            ? "Thêm sinh viên hoặc nhập danh sách ở tab Sinh viên, hoặc cấp mã lớp ở Cài đặt để sinh viên tự vào."
            : "Lớp mới chưa có sinh viên hay nhóm là trạng thái hợp lệ."
        }
      />
    );
  }

  const withoutProject = teams.data?.teams.filter((team) => team.project === null) ?? [];
  const base = `/teacher/courses/${course.courseId}`;

  const renderWithoutProject = () => {
    if (teams.isPending) return <output className="text-muted-foreground">Đang tải…</output>;
    if (teams.isError) {
      return <p className="text-muted-foreground">Không tải được danh sách nhóm.</p>;
    }
    if (withoutProject.length === 0) {
      return <p className="text-muted-foreground">Mọi nhóm trong lớp đều đã có project.</p>;
    }
    return (
      <ul className="space-y-1">
        {withoutProject.map((team) => (
          <li key={team.teamId} className="flex items-center justify-between gap-2">
            <span className="font-medium">{team.name}</span>
            <Badge variant="outline">{team.memberCount} thành viên</Badge>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="space-y-6">
      <section aria-label="Chỉ số của lớp" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Sinh viên" value={course.studentCount} />
        <StatCard label="Chưa có nhóm" value={course.studentsWithoutTeam ?? <NoData />} />
        <StatCard label="Nhóm" value={course.teamCount} />
        <StatCard
          label="Nhóm có tín hiệu cần chú ý"
          value={course.teamsWithSignals ?? <NoData />}
          tone={course.teamsWithSignals ? "attention" : "default"}
          hint="Xem nguyên nhân ở mục Giám sát"
        />
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-base">Quy định nhóm và tham gia lớp</CardTitle>
          <Badge variant="secondary">{course.classroom ? "Sửa ở Cài đặt" : "Chỉ xem"}</Badge>
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
                  <span className="text-base font-normal text-muted-foreground">{joinCodeText(course)}</span>
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
          {course.classroom ? null : (
            <p className="mt-4 text-xs text-muted-foreground">
              Chỉnh sửa quy định, hạn lập nhóm và trạng thái nhận sinh viên sẽ khả dụng ở giai đoạn
              sau.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Nhóm chưa có project</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {renderWithoutProject()}
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

      {course.classroom ? <ActivityList scope={{ classId: course.courseId }} title="Lịch sử lớp" /> : null}
    </div>
  );
}
