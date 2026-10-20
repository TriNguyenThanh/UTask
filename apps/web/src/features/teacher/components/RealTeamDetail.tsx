import { Link, useParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ActivityList } from "@/features/teacher/components/ActivityList";
import { PersonAvatar, TeacherQueryError } from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import { UNKNOWN_NAME } from "@/lib/api/classroom/teacherLoaders";
import { useTeacherTeams } from "@/lib/query/teacherFlowHooks";

/**
 * Team page for the real Classroom service: members and the team's change
 * history. Project, progress and signals belong to Work and are not shown as
 * if they were zero.
 */
export function RealTeamDetail() {
  const { teamId = "" } = useParams();
  const course = useTeacherCourseContext();
  const teams = useTeacherTeams(course.courseId);
  const backLink = (
    <Button asChild variant="outline" size="sm">
      <Link to={`/teacher/courses/${course.courseId}/teams`}>Về danh sách nhóm</Link>
    </Button>
  );

  if (teams.isPending) {
    return <PageSkeleton label="Đang tải thông tin nhóm" />;
  }
  if (teams.isError) {
    return <TeacherQueryError error={teams.error} onRetry={() => void teams.refetch()} />;
  }
  const team = teams.data.teams.find((candidate) => candidate.teamId === teamId);
  if (!team) {
    return (
      <EmptyState
        title="Không tìm thấy nhóm"
        description="Nhóm không tồn tại, đã được lưu trữ hoặc không thuộc lớp này."
        action={backLink}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-bold tracking-tight">{team.name}</h2>
          <p className="text-sm text-muted-foreground">
            {team.memberCount}/{team.maxMembers} thành viên.{" "}
            {team.project
              ? <>
                  Dự án:{" "}
                  <Link to={`/projects/${team.project.projectId}/info`} className="font-mono font-medium hover:underline">
                    {team.project.key}
                  </Link>{" "}
                  {team.project.name}. Tiến độ chưa có dữ liệu (cần Work Service).
                </>
              : "Project và tiến độ chưa có dữ liệu (cần Work Service)."}
          </p>
        </div>
        {backLink}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Thành viên</CardTitle>
        </CardHeader>
        <CardContent>
          {team.members.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nhóm chưa có thành viên.</p>
          ) : (
            <ul className="divide-y text-sm">
              {team.members.map((member) => (
                <li key={member.userId} className="flex items-center justify-between gap-2 py-2">
                  <span className="flex items-center gap-2.5">
                    <PersonAvatar name={member.name || UNKNOWN_NAME} />
                    <span className="font-medium">{member.name || UNKNOWN_NAME}</span>
                    <span className="font-mono text-xs text-muted-foreground">{member.studentCode}</span>
                  </span>
                  {member.role === "leader" ? <Badge>Leader</Badge> : <span className="text-muted-foreground">Thành viên</span>}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ActivityList scope={{ groupId: team.teamId }} title="Lịch sử nhóm" />
    </div>
  );
}
