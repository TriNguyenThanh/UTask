import { Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AddStudentDialog } from "@/features/teacher/components/AddStudentDialog";
import { Input } from "@/components/ui/input";
import { PersonAvatar, TeacherQueryError } from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import type { TeacherStudent } from "@/lib/api/teacherFlow";
import { useTeacherStudents } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

type TeamFilter = "all" | "has-team" | "no-team";

function NoStudents({ hasStudents }: Readonly<{ hasStudents: boolean }>) {
  if (!hasStudents) {
    return (
      <EmptyState
        title="Lớp chưa có sinh viên"
        description="Danh sách sẽ hiển thị tại đây khi sinh viên được thêm vào lớp."
      />
    );
  }
  return (
    <EmptyState
      title="Không có sinh viên khớp bộ lọc"
      description="Thử đổi từ khóa hoặc bộ lọc nhóm."
    />
  );
}

function parseFilter(value: string | null): TeamFilter {
  return value === "has-team" || value === "no-team" ? value : "all";
}

function teamCell(student: TeacherStudent) {
  if (student.team) {
    return <span className="font-medium">{student.team.name}</span>;
  }
  if (student.pendingTeam) {
    return (
      <span className="text-muted-foreground">
        Chờ duyệt vào {student.pendingTeam.name}
      </span>
    );
  }
  return (
    <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-900">
      Chưa có nhóm
    </Badge>
  );
}

function roleCell(student: TeacherStudent) {
  if (!student.team) return <span className="text-muted-foreground">—</span>;
  return student.team.role === "leader" ? <Badge>Leader</Badge> : <span>Thành viên</span>;
}

export function Component() {
  const course = useTeacherCourseContext();
  const students = useTeacherStudents(course.courseId);
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const filter = parseFilter(searchParams.get("team"));

  function setParam(key: string, value: string, empty: string) {
    const params = new URLSearchParams(searchParams);
    if (value === empty) params.delete(key);
    else params.set(key, value);
    setSearchParams(params);
  }

  if (students.isPending) {
    return <PageSkeleton label="Đang tải danh sách sinh viên" />;
  }
  if (students.isError) {
    return <TeacherQueryError error={students.error} onRetry={() => void students.refetch()} />;
  }

  const all = students.data.students;
  const withTeam = all.filter((student) => student.team !== null).length;
  const needle = query.trim().toLowerCase();
  const visible = all.filter((student) => {
    if (filter === "has-team" && student.team === null) return false;
    if (filter === "no-team" && student.team !== null) return false;
    if (!needle) return true;
    return [student.name, student.email, student.studentCode].some((value) =>
      value.toLowerCase().includes(needle),
    );
  });

  const chips: { id: TeamFilter; label: string; count: number }[] = [
    { id: "all", label: "Tất cả", count: all.length },
    { id: "no-team", label: "Chưa có nhóm", count: all.length - withTeam },
    { id: "has-team", label: "Đã có nhóm", count: withTeam },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex w-full flex-col gap-1 sm:w-80">
          <label htmlFor="teacher-student-search" className="text-xs font-medium text-muted-foreground">
            Tìm sinh viên
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="teacher-student-search"
              type="search"
              className="pl-9"
              placeholder="Tên, email hoặc MSSV"
              value={query}
              onChange={(event) => setParam("q", event.target.value, "")}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <AddStudentDialog courseName={course.name} />
          <Button asChild>
            <Link to={`/teacher/courses/${course.courseId}/students/import`}>Nhập danh sách</Link>
          </Button>
        </div>
      </div>

      <fieldset aria-label="Lọc theo nhóm" className="m-0 flex min-w-0 flex-wrap gap-1.5 border-0 p-0">
        {chips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            aria-pressed={filter === chip.id}
            onClick={() => setParam("team", chip.id, "all")}
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
        <NoStudents hasStudents={all.length > 0} />
      ) : (
        <>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {visible.length} / {all.length} sinh viên
          </p>

          <div className="hidden overflow-x-auto rounded-lg border bg-card md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold">MSSV</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Họ và tên</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Email</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Nhóm</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Vai trò trong nhóm</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {visible.map((student) => (
                  <tr
                    key={student.userId}
                    className={cn(!student.team && !student.pendingTeam && "bg-amber-50/40")}
                  >
                    <td className="px-4 py-3 font-mono text-xs">{student.studentCode}</td>
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-2.5">
                        <PersonAvatar name={student.name} />
                        <span className="font-medium">{student.name}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{student.email}</td>
                    <td className="px-4 py-3">{teamCell(student)}</td>
                    <td className="px-4 py-3">{roleCell(student)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="divide-y rounded-lg border bg-card md:hidden">
            {visible.map((student) => (
              <li key={student.userId} className="space-y-1 p-4 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="flex items-center gap-2.5">
                    <PersonAvatar name={student.name} />
                    <span className="font-medium">{student.name}</span>
                  </span>
                  {student.team?.role === "leader" ? <Badge>Leader</Badge> : null}
                </div>
                <p className="text-muted-foreground">
                  {student.studentCode} • {student.email}
                </p>
                <p>
                  <span className="text-muted-foreground">Nhóm: </span>
                  {teamCell(student)}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
