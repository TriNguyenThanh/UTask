import { Search } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { FilterSelect } from "@/features/teacher/components/FilterSelect";
import {
  ProgressMeter,
  SignalList,
  StatCard,
  TeacherQueryError,
  activityText,
  formatDate,
} from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import type { TeacherOversightRow } from "@/lib/api/teacherFlow";
import { useTeacherOversight } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

type SignalFilter = "all" | "with-signals" | "no-signals";
type SortKey = "signals" | "progress" | "name";

function parseFilter(value: string | null): SignalFilter {
  return value === "with-signals" || value === "no-signals" ? value : "all";
}

function parseSort(value: string | null): SortKey {
  return value === "progress" || value === "name" ? value : "signals";
}

/** Unknown progress sorts last: it is "no data", not "lowest". */
function compare(sort: SortKey, a: TeacherOversightRow, b: TeacherOversightRow): number {
  if (sort === "name") return a.name.localeCompare(b.name, "vi");
  if (sort === "progress") {
    if (a.progress === null && b.progress === null) return a.name.localeCompare(b.name, "vi");
    if (a.progress === null) return 1;
    if (b.progress === null) return -1;
    return a.progress.percent - b.progress.percent;
  }
  return b.signals.length - a.signals.length || a.name.localeCompare(b.name, "vi");
}

function ProjectCell({ row }: { row: TeacherOversightRow }) {
  return (
    <div>
      <p className="font-semibold">{row.name}</p>
      {row.project ? (
        <p className="text-xs text-muted-foreground">
          {row.project.key} • {row.project.name}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">Chưa có project</p>
      )}
      <p className="text-xs text-muted-foreground">{row.memberCount} thành viên</p>
    </div>
  );
}

function WorkCell({ row }: { row: TeacherOversightRow }) {
  return (
    <div className="space-y-1 text-sm">
      <ProgressMeter
        label={`Tiến độ ${row.name}`}
        progress={row.progress}
        emptyText={row.project ? "Chưa có dữ liệu tiến độ" : "Chưa có project để đo tiến độ"}
      />
      {row.issues ? (
        <p className="text-xs text-muted-foreground">
          {row.issues.done}/{row.issues.total} issue đã hoàn thành
        </p>
      ) : null}
      {row.sprint ? (
        <p className="text-xs text-muted-foreground">
          {row.sprint.name} • kết thúc {formatDate(row.sprint.endsAt)}
        </p>
      ) : row.project ? (
        <p className="text-xs text-muted-foreground">Không có Sprint đang chạy</p>
      ) : null}
    </div>
  );
}

export function Component() {
  const course = useTeacherCourseContext();
  const oversight = useTeacherOversight(course.courseId);
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const filter = parseFilter(searchParams.get("filter"));
  const sort = parseSort(searchParams.get("sort"));

  function setParam(key: string, value: string, empty: string) {
    const params = new URLSearchParams(searchParams);
    if (value === empty) params.delete(key);
    else params.set(key, value);
    setSearchParams(params);
  }

  if (oversight.isPending) {
    return <PageSkeleton label="Đang tải giám sát tiến độ" />;
  }
  if (oversight.isError) {
    return <TeacherQueryError error={oversight.error} onRetry={() => void oversight.refetch()} />;
  }

  const { teams, staleAfterDays } = oversight.data;
  if (teams.length === 0) {
    return (
      <EmptyState
        title="Lớp chưa có nhóm để giám sát"
        description="Khi lớp có nhóm và project, tiến độ và tín hiệu sẽ hiển thị tại đây."
      />
    );
  }

  const withSignals = teams.filter((row) => row.signals.length > 0).length;
  const withoutProject = teams.filter((row) => row.project === null).length;
  const needle = query.trim().toLowerCase();
  const visible = teams
    .filter((row) => {
      if (filter === "with-signals" && row.signals.length === 0) return false;
      if (filter === "no-signals" && row.signals.length > 0) return false;
      if (!needle) return true;
      return [row.name, row.project?.name ?? "", row.project?.key ?? ""].some((value) =>
        value.toLowerCase().includes(needle),
      );
    })
    .sort((a, b) => compare(sort, a, b));

  const chips: { id: SignalFilter; label: string; count: number }[] = [
    { id: "all", label: "Tất cả", count: teams.length },
    { id: "with-signals", label: "Có tín hiệu", count: withSignals },
    { id: "no-signals", label: "Chưa có tín hiệu", count: teams.length - withSignals },
  ];

  return (
    <div className="space-y-6">
      <section aria-label="Tóm tắt giám sát" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard label="Tổng số nhóm" value={teams.length} />
        <StatCard
          label="Có tín hiệu cần chú ý"
          value={withSignals}
          tone={withSignals > 0 ? "attention" : "default"}
          hint="Theo quy tắc cố định bên dưới"
        />
        <StatCard
          label="Chưa có tín hiệu"
          value={teams.length - withSignals}
          hint="Không có nghĩa là nhóm đang tốt"
        />
        <StatCard label="Chưa có project" value={withoutProject} />
      </section>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex w-full flex-col gap-1 sm:w-80">
          <label htmlFor="teacher-oversight-search" className="text-xs font-medium text-muted-foreground">
            Tìm nhóm
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              id="teacher-oversight-search"
              type="search"
              className="pl-9"
              placeholder="Tên nhóm hoặc project"
              value={query}
              onChange={(event) => setParam("q", event.target.value, "")}
            />
          </div>
        </div>
        <FilterSelect
          label="Sắp xếp"
          value={sort}
          onChange={(value) => setParam("sort", value, "signals")}
          className="w-full sm:w-56"
          options={[
            { value: "signals", label: "Nhiều tín hiệu nhất" },
            { value: "progress", label: "Tiến độ thấp nhất" },
            { value: "name", label: "Tên nhóm" },
          ]}
        />
      </div>

      <div role="group" aria-label="Lọc theo tín hiệu" className="flex flex-wrap gap-1.5">
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
      </div>

      {visible.length === 0 ? (
        <EmptyState
          title="Không có nhóm khớp bộ lọc"
          description="Thử đổi từ khóa hoặc bộ lọc tín hiệu."
        />
      ) : (
        <>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Hiển thị {visible.length} / {teams.length} nhóm
          </p>

          <div className="hidden overflow-x-auto rounded-lg border bg-card md:block">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted text-[11px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold">Nhóm và project</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Tiến độ</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Hoạt động gần nhất</th>
                  <th scope="col" className="px-4 py-3 font-semibold">Tín hiệu cần chú ý</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {visible.map((row) => (
                  <tr key={row.teamId} className="align-top">
                    <td className="px-4 py-3"><ProjectCell row={row} /></td>
                    <td className="min-w-56 px-4 py-3"><WorkCell row={row} /></td>
                    <td className="px-4 py-3 text-muted-foreground">{activityText(row.lastActivity)}</td>
                    <td className="min-w-56 px-4 py-3">
                      <SignalList signals={row.signals} emptyText="Chưa phát hiện tín hiệu" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="space-y-3 md:hidden">
            {visible.map((row) => (
              <li key={row.teamId} className="space-y-3 rounded-lg border bg-card p-4 text-sm">
                <ProjectCell row={row} />
                <WorkCell row={row} />
                <p className="text-xs text-muted-foreground">{activityText(row.lastActivity)}</p>
                <SignalList signals={row.signals} emptyText="Chưa phát hiện tín hiệu" />
              </li>
            ))}
          </ul>
        </>
      )}

      <section
        aria-label="Cách tính tín hiệu"
        className="space-y-1 rounded-lg border bg-muted/50 p-4 text-xs text-muted-foreground"
      >
        <h2 className="text-sm font-semibold text-foreground">Cách tính tín hiệu</h2>
        <p>
          Tín hiệu tính bằng quy tắc cố định trên dữ liệu issue và nhóm, không dùng AI và không
          quy đổi thành điểm:
        </p>
        <ul className="list-disc space-y-0.5 pl-5">
          <li>Nhóm chưa có project, hoặc project chưa có dữ liệu để đo tiến độ.</li>
          <li>Không có cập nhật issue nào trong {staleAfterDays} ngày gần nhất.</li>
          <li>Nhóm có ít thành viên hơn mức tối thiểu của lớp ({course.teamSize.min}).</li>
        </ul>
        <p>
          Tiến độ tính theo điểm Sprint đang chạy; nếu không có thì theo tỷ lệ issue hoàn thành.
          Dữ liệu này là Demo MSW, chưa có commit/PR hay cảnh báo từ AI.
        </p>
        <Badge variant="outline" className="mt-1">
          Chỉ xem
        </Badge>
      </section>
    </div>
  );
}
