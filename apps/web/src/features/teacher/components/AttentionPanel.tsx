import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/AuthProvider";
import { SignalList, courseLabel, formatDateTime } from "@/features/teacher/components/shared";
import { useApiClient } from "@/lib/api/ApiClientProvider";
import {
  teacherOversightRequest,
  type TeacherCourseSummary,
  type TeacherOversightRow,
} from "@/lib/api/teacherFlow";
import { teacherKeys } from "@/lib/query/teacherFlowHooks";

const MAX_TEAMS_SHOWN = 6;

interface FlaggedTeam {
  course: TeacherCourseSummary;
  row: TeacherOversightRow;
}

/**
 * Cross-class summary of teams with a signal. It reads the same oversight data
 * as each class's Giám sát tab, one request per class, and each class fails on
 * its own. It is a to-look-at list, not a ranking: no scores, no AI, and "no
 * signal" is never presented as "doing well".
 */
export function AttentionPanel({ courses }: Readonly<{ courses: TeacherCourseSummary[] }>) {
  const client = useApiClient();
  const { user } = useAuth();
  const userId = user?.id ?? "anonymous";
  const results = useQueries({
    queries: courses.map((course) => ({
      queryKey: teacherKeys.oversight(userId, course.courseId),
      queryFn: () => teacherOversightRequest(client, course.courseId),
      enabled: user !== null,
    })),
  });

  const pending = results.some((result) => result.isPending);
  const failed = courses.filter((_, index) => results[index]?.isError);
  const flagged: FlaggedTeam[] = courses
    .flatMap((course, index) =>
      (results[index]?.data?.teams ?? [])
        .filter((row) => row.signals.length > 0)
        .map((row) => ({ course, row })),
    )
    .sort((a, b) => b.row.signals.length - a.row.signals.length || a.row.name.localeCompare(b.row.name, "vi"));
  const asOf = results.find((result) => result.data)?.data?.asOf;
  const shown = flagged.slice(0, MAX_TEAMS_SHOWN);

  return (
    <section aria-label="Cần chú ý">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Cần chú ý ({flagged.length} nhóm)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Tổng hợp theo quy tắc cố định, không dùng AI và không quy ra điểm. Không có tín hiệu không có
            nghĩa là nhóm đang tốt.
            {asOf ? ` Tính tại ${formatDateTime(asOf)}.` : ""}
          </p>

          {pending ? (
            <output aria-label="Đang tải tín hiệu" className="block space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </output>
          ) : null}

          {failed.length > 0 ? (
            <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              <p className="font-medium">Không tải được tín hiệu của {failed.length} lớp:</p>
              <ul className="mt-1 list-disc pl-5">
                {failed.map((course) => (
                  <li key={course.courseId}>{courseLabel(course)} — {course.name}</li>
                ))}
              </ul>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="mt-2"
                onClick={() => results.forEach((result) => result.isError && void result.refetch())}
              >
                Thử lại
              </Button>
            </div>
          ) : null}

          {!pending && flagged.length === 0 && failed.length === 0 ? (
            <p className="text-sm text-muted-foreground">Hiện chưa có nhóm nào có tín hiệu cần chú ý.</p>
          ) : null}

          <ul className="space-y-4">
            {shown.map(({ course, row }) => (
              <li key={`${course.courseId}:${row.teamId}`} className="space-y-2 rounded-md border bg-background p-3">
                <p className="text-sm">
                  <Link
                    to={`/teacher/courses/${course.courseId}/teams/${row.teamId}`}
                    className="font-semibold hover:underline"
                  >
                    {row.name}
                  </Link>{" "}
                  <span className="text-muted-foreground">• {courseLabel(course)}</span>
                </p>
                <SignalList signals={row.signals} subject={`${row.name}, ${courseLabel(course)}`} />
              </li>
            ))}
          </ul>

          {flagged.length > shown.length ? (
            <p className="text-xs text-muted-foreground">
              Còn {flagged.length - shown.length} nhóm khác có tín hiệu. Xem đủ ở mục Giám sát của từng lớp.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
