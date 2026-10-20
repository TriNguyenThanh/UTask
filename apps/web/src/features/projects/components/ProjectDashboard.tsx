import type { ReactNode } from "react";

import type { DashboardDto, ProjectMemberDto, StateGroupDto } from "@/lib/api/work/dto";
import { useProjectDashboard } from "@/lib/query/workSprintHooks";

const GROUP_LABEL: Record<StateGroupDto, string> = {
  BACKLOG: "Backlog",
  UNSTARTED: "Chưa bắt đầu",
  REVIEW: "Đang review",
  STARTED: "Đang làm",
  COMPLETED: "Hoàn thành",
  CANCELLED: "Đã hủy",
};

function Stat({ label, value }: Readonly<{ label: string; value: ReactNode }>) {
  return (
    <div className="rounded-md border bg-muted/20 px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}

/** Tên người nhận việc: lấy từ danh sách thành viên; thiếu thì hiện mã rút gọn thay vì để trống. */
export function assigneeLabel(userId: string, members: readonly Pick<ProjectMemberDto, "user_id" | "display_name">[]) {
  const name = members.find((member) => member.user_id === userId)?.display_name;
  return name ? name : `Thành viên ${userId.slice(0, 6)}`;
}

/**
 * Phần trăm capacity đã dùng = điểm đã giao / capacity tuần. **Ước lượng phía client**: server không
 * trả số này. `null` khi chưa đặt capacity hoặc capacity bằng 0 (không chia được).
 */
export function capacityUsagePercent(allocatedPoints: number, weeklyCapacity: number | null): number | null {
  if (weeklyCapacity === null || weeklyCapacity <= 0) return null;
  return Math.round((allocatedPoints / weeklyCapacity) * 100);
}

const formatPercent = (value: number | null) => (value === null ? "—" : `${value}%`);

/** Phần thân của bảng điều khiển; tách ra để kiểm thử không cần gọi API. */
export function DashboardBody({
  dashboard,
  members,
}: Readonly<{ dashboard: DashboardDto; members: readonly ProjectMemberDto[] }>) {
  const { totals } = dashboard;
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          label="Hoàn thành"
          value={totals.completion_percent === null ? "—" : `${Math.round(totals.completion_percent)}%`}
        />
        <Stat label="Việc xong" value={`${totals.completed_work_item_count}/${totals.work_item_count}`} />
        <Stat label="Điểm xong" value={`${totals.completed_estimate_points}/${totals.known_estimate_points}`} />
        <Stat label="Chưa ước lượng" value={totals.unestimated_count} />
        <Stat label="Bị chặn" value={totals.blocked_task_count} />
        <Stat label="Bị chặn do phụ thuộc" value={totals.dependency_blocked_task_count} />
        <Stat label="Quá hạn" value={totals.overdue_task_count} />
        <Stat label="Điểm chưa giao" value={dashboard.unassigned_estimate_points} />
      </dl>

      <div>
        <h3 className="mb-1 text-sm font-medium">Theo trạng thái</h3>
        <ul className="flex flex-wrap gap-2 text-sm">
          {dashboard.state_distribution.map((row) => (
            <li key={row.group} className="rounded-full border px-3 py-0.5">
              {GROUP_LABEL[row.group]}: {row.work_item_count}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-medium">Khối lượng theo người</h3>
        {dashboard.assignee_distribution.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có việc nào được giao.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Người nhận</th>
                  <th className="px-3 py-2 text-left font-medium">Việc</th>
                  <th className="px-3 py-2 text-left font-medium">Điểm</th>
                  <th className="px-3 py-2 text-left font-medium">Chưa ước lượng</th>
                  <th className="px-3 py-2 text-left font-medium">Giờ/tuần</th>
                  <th className="px-3 py-2 text-left font-medium" title="Điểm đã giao / capacity tuần; ước lượng phía client">
                    Dùng capacity (ước lượng)
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {dashboard.assignee_distribution.map((row) => (
                  <tr key={row.user_id}>
                    <td className="px-3 py-2">{assigneeLabel(row.user_id, members)}</td>
                    <td className="px-3 py-2">{row.assigned_work_item_count}</td>
                    <td className="px-3 py-2">{row.allocated_estimate_points}</td>
                    <td className="px-3 py-2">{row.unestimated_work_item_count}</td>
                    <td className="px-3 py-2">{row.weekly_capacity ?? "—"}</td>
                    <td className="px-3 py-2">{formatPercent(capacityUsagePercent(row.allocated_estimate_points, row.weekly_capacity))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function ProjectDashboardSection({
  projectId,
  members,
}: Readonly<{ projectId: string; members: readonly ProjectMemberDto[] }>) {
  const query = useProjectDashboard(projectId);
  return (
    <section className="rounded-md border bg-card" aria-label="Bảng điều khiển dự án">
      <div className="border-b px-4 py-3">
        <h2 className="font-semibold">Tổng quan tiến độ</h2>
        <p className="text-xs text-muted-foreground">Tính trên các issue đang hoạt động của dự án.</p>
      </div>
      <div className="p-4">
        {query.isPending ? <p className="text-sm text-muted-foreground">Đang tải số liệu…</p> : null}
        {query.isError ? <p className="text-sm text-destructive">Không tải được số liệu tổng quan.</p> : null}
        {query.data ? <DashboardBody dashboard={query.data} members={members} /> : null}
      </div>
    </section>
  );
}
