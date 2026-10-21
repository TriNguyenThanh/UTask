import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { PageSkeleton } from "@/components/feedback/PageSkeleton";
import { segmentedTabClass, segmentedTabsListClass } from "@/components/navigation/segmentedTabs";
import { sectionPanelClass } from "@/components/layout/sectionPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { WorkProjectCard } from "@/lib/api/work/adapters";
import { useWorkProjects } from "@/lib/query/workHooks";
import { cn } from "@/lib/utils";

type Tab = "active" | "archived";

function matchesSearch(card: WorkProjectCard, q: string): boolean {
  if (!q) return true;
  const lower = q.toLowerCase();
  return (
    card.identifier.toLowerCase().includes(lower) ||
    card.name.toLowerCase().includes(lower) ||
    card.classCode.toLowerCase().includes(lower) ||
    card.courseCode.toLowerCase().includes(lower) ||
    card.groupName.toLowerCase().includes(lower)
  );
}

function RoleLabel({ role }: { role: WorkProjectCard["myRole"] }) {
  if (role === "LEADER") return <Badge>Trưởng nhóm</Badge>;
  if (role === "MEMBER") return <Badge variant="secondary">Thành viên</Badge>;
  return null;
}

function ProjectCard({ card }: { card: WorkProjectCard }) {
  const courseLine = [card.courseCode, card.classCode, card.className].filter(Boolean).join(" · ");
  return (
    <div className="rounded-lg border bg-card p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="font-mono text-xs">{card.identifier}</Badge>
            <RoleLabel role={card.myRole} />
          </div>
          <Link
            to={`/projects/${card.projectId}`}
            className="text-base font-semibold hover:underline"
          >
            {card.name}
          </Link>
        </div>
      </div>
      {courseLine && <p className="text-sm text-muted-foreground">{courseLine}</p>}
      {card.groupName && <p className="text-sm text-muted-foreground">Nhóm: {card.groupName}</p>}
      {card.repository && (
        <p className="text-xs text-muted-foreground font-mono">{card.repository}</p>
      )}
      <div className="pt-1">
        <Button asChild size="sm" variant="outline">
          <Link to={`/projects/${card.projectId}`}>Vào dự án</Link>
        </Button>
      </div>
    </div>
  );
}

export function RealProjectList() {
  const query = useWorkProjects();
  const [tab, setTab] = useState<Tab>("active");
  const [search, setSearch] = useState("");

  if (query.isPending) return <PageSkeleton label="Đang tải danh sách dự án" />;
  if (query.isError) {
    return (
      <div className="p-4 md:p-6">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </div>
    );
  }

  const { cards, partial } = query.data;
  const tabCards = cards.filter((card) => (tab === "archived") === card.archived);
  const visible = tabCards.filter((card) => matchesSearch(card, search.trim()));

  return (
    <div className="page-container space-y-5 p-4 md:p-6">
      {partial && (
        <div className="rounded-md border border-yellow-300 bg-yellow-50 px-4 py-2 text-sm text-yellow-800">
          Danh sách có thể thiếu dự án của lớp bạn phụ trách vì hệ thống chưa xác minh được quyền giảng viên.
        </div>
      )}

      <div className={cn("space-y-4", sectionPanelClass)}>
        <div className="flex flex-wrap items-center gap-3">
          <div role="tablist" className={segmentedTabsListClass}>
            <button
              role="tab"
              aria-selected={tab === "active"}
              className={segmentedTabClass(tab === "active")}
              onClick={() => setTab("active")}
            >
              Đang hoạt động
            </button>
            <button
              role="tab"
              aria-selected={tab === "archived"}
              className={segmentedTabClass(tab === "archived")}
              onClick={() => setTab("archived")}
            >
              Đã lưu trữ
            </button>
          </div>
          <Input
            placeholder="Tìm theo mã, tên, lớp, môn, nhóm…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 w-60"
          />
        </div>

        {cards.length === 0 ? (
          <EmptyState
            title="Chưa có dự án"
            description="Bạn chưa thuộc dự án nào. Trưởng nhóm tạo dự án từ trang nhóm của môn học."
            action={
              <Button asChild variant="outline">
                <Link to="/courses">Đến trang môn học</Link>
              </Button>
            }
          />
        ) : visible.length === 0 ? (
          <EmptyState
            description={
              search
                ? "Không tìm thấy dự án phù hợp với từ khóa."
                : tab === "archived"
                  ? "Không có dự án đã lưu trữ."
                  : "Không có dự án đang hoạt động."
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((card) => (
              <ProjectCard key={card.projectId} card={card} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
