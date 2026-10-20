import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProjectDashboard } from "@/lib/query/workSprintHooks";

function Stat({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-bold">{value}</dd>
    </div>
  );
}

/**
 * Tiến độ dự án của nhóm, đọc từ tổng quan của Work (số liệu server tính, không tự tính lại).
 * Lỗi tải chỉ làm khối này báo lỗi, không ảnh hưởng phần còn lại của trang.
 */
export function RealTeamProgress({ projectId }: Readonly<{ projectId: string }>) {
  const dashboard = useProjectDashboard(projectId);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Tiến độ dự án</CardTitle>
      </CardHeader>
      <CardContent>
        {dashboard.isPending ? <p className="text-sm text-muted-foreground">Đang tải tiến độ…</p> : null}
        {dashboard.isError ? (
          <p role="alert" className="text-sm text-destructive">
            Không tải được tiến độ dự án.
          </p>
        ) : null}
        {dashboard.data ? (
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Task" value={String(dashboard.data.totals.task_count)} />
            <Stat
              label="Hoàn thành"
              value={dashboard.data.totals.completion_percent === null ? "Chưa có việc" : `${dashboard.data.totals.completion_percent}%`}
            />
            <Stat label="Quá hạn" value={String(dashboard.data.totals.overdue_task_count)} />
            <Stat label="Đang bị chặn" value={String(dashboard.data.totals.blocked_task_count)} />
          </dl>
        ) : null}
      </CardContent>
    </Card>
  );
}
