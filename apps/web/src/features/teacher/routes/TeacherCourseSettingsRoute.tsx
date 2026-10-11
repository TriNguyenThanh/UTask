import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CopyJoinCodeButton } from "@/features/teacher/components/JoinCode";
import { DisabledAction, courseLabel } from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";

const CODE_CHANGE_UNAVAILABLE =
  "Đổi mã chưa khả dụng: chưa có hợp đồng API đổi mã tham gia. Khi bật, thao tác này sẽ cần xác nhận vì mã cũ ngừng dùng được.";
const CODE_DISABLE_UNAVAILABLE =
  "Vô hiệu mã chưa khả dụng: chưa có hợp đồng API. Khi bật, thao tác này sẽ cần xác nhận vì sinh viên mới không thể vào lớp bằng mã này nữa.";

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
 * T10. Read-only on purpose: the only write-looking controls (change or
 * disable the join code) are disabled with their reason. Having an API to
 * create a class says nothing about editing or deleting one, so no edit or
 * delete control exists here.
 */
export function Component() {
  const course = useTeacherCourseContext();

  return (
    <div className="max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Thông tin lớp</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
            <Fact label="Tên lớp">{course.name}</Fact>
            <Fact label="Mã môn và lớp">{courseLabel(course)}</Fact>
            <Fact label="Học kỳ">{course.term}</Fact>
            <Fact label="Sĩ số nhóm">
              {course.teamSize.min}–{course.teamSize.max} thành viên
            </Fact>
          </dl>
          <p className="mt-4 text-xs text-muted-foreground">
            Sửa thông tin lớp chưa khả dụng vì chưa có hợp đồng API sửa lớp.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mã tham gia</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {course.joinCode ? (
            <div className="flex flex-wrap items-center gap-3">
              <span
                aria-label="Mã tham gia hiện tại"
                className="rounded-md border bg-muted/50 px-3 py-1.5 font-mono text-base font-semibold"
              >
                {course.joinCode}
              </span>
              <CopyJoinCodeButton code={course.joinCode} />
              <Badge variant="outline" className="border-emerald-300 bg-emerald-50 text-emerald-900">
                Đang dùng được
              </Badge>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Lớp này chưa có mã tham gia.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <DisabledAction reason={CODE_CHANGE_UNAVAILABLE}>Đổi mã</DisabledAction>
            <DisabledAction reason={CODE_DISABLE_UNAVAILABLE}>Vô hiệu mã</DisabledAction>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Giảng viên phụ trách</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {course.instructors.map((instructor) => (
              <li key={instructor.userId} className="flex items-center gap-2">
                {instructor.name}
                {instructor.isOwner ? <Badge variant="secondary">Phụ trách chính</Badge> : null}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            Không có thao tác xóa lớp hay đổi giảng viên ở đây.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
