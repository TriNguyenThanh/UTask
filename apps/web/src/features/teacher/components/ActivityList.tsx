import { ErrorState } from "@/components/feedback/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UNKNOWN_NAME } from "@/lib/api/classroom/teacherLoaders";
import { useActivities, useUserNames } from "@/lib/query/teacherClassHooks";

/** Mô tả tiếng Việt cho `verb` của Classroom; verb lạ hiện nguyên mã để không che mất sự kiện. */
const VERB_LABEL: Record<string, string> = {
  "class.created": "Tạo lớp",
  "class.update": "Sửa thông tin lớp",
  "class.state": "Đổi trạng thái lớp",
  "class.lock-grouping": "Chốt giai đoạn lập nhóm",
  "class.code.changed": "Cấp hoặc tắt mã tham gia lớp",
  "class.teacher": "Đổi giảng viên phụ trách",
  "class.teacher.changed": "Đổi giảng viên phụ trách",
  "enrollment.added": "Giảng viên thêm sinh viên vào lớp",
  "enrollment.joined": "Sinh viên vào lớp bằng mã",
  "enrollment.exited": "Sinh viên rời hoặc bị loại khỏi lớp",
  "group.created": "Tạo nhóm",
  "group.updated": "Sửa thông tin nhóm",
  "group.code.changed": "Cấp hoặc tắt mã mời nhóm",
  "group.leader.transferred": "Chuyển quyền Leader",
  "group.member.joined": "Thành viên vào nhóm",
  "group.member.assigned": "Giảng viên xếp thành viên vào nhóm",
  "group.member.left": "Thành viên rời nhóm",
  "group.member.removed": "Thành viên bị loại khỏi nhóm",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

/**
 * Lịch sử thay đổi của một lớp hoặc nhóm (Classroom `activities`). Chỉ hiện
 * việc gì, ai làm, lúc nào: nội dung `changes` chưa có hợp đồng nên không đọc (B4f).
 */
export function ActivityList({
  scope,
  title,
}: Readonly<{ scope: { classId: string } | { groupId: string }; title: string }>) {
  const activities = useActivities(scope);
  const actorIds = (activities.data ?? []).flatMap((activity) => (activity.actor_user_id ? [activity.actor_user_id] : []));
  const names = useUserNames(actorIds);

  let body;
  if (activities.isPending) {
    body = <Skeleton className="h-16 w-full" />;
  } else if (activities.isError) {
    body = <ErrorState error={activities.error} onRetry={() => void activities.refetch()} />;
  } else if (activities.data.length === 0) {
    body = <p className="text-sm text-muted-foreground">Chưa có thay đổi nào được ghi lại.</p>;
  } else {
    body = (
      <ul className="divide-y text-sm">
        {activities.data.map((activity) => (
          <li key={activity.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2">
            <span>
              <span className="font-medium">{VERB_LABEL[activity.verb] ?? activity.verb}</span>
              <span className="text-muted-foreground">
                {" — "}
                {activity.actor_user_id ? (names.data?.get(activity.actor_user_id) ?? UNKNOWN_NAME) : "Hệ thống"}
              </span>
            </span>
            <time dateTime={activity.created_at} className="text-xs text-muted-foreground">
              {formatTime(activity.created_at)}
            </time>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
