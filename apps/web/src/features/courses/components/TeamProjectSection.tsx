import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CreateProjectDialog } from "@/features/projects/components/CreateProjectDialog";
import { useGroupProjects } from "@/lib/query/workHooks";

/**
 * Hiển thị danh sách dự án của nhóm (từ Work Service) trong TeamHubView.
 * Chỉ render khi `isRealService("work")` — kiểm tra do caller thực hiện.
 */
export function TeamProjectSection({
  groupId,
  isLeader,
}: Readonly<{ groupId: string; isLeader: boolean }>) {
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isError, isPending } = useGroupProjects();

  if (isError) {
    return (
      <section className="space-y-2 pt-2" aria-label="Dự án nhóm">
        <p className="text-sm text-muted-foreground">Chưa tải được dự án của nhóm.</p>
      </section>
    );
  }

  const projects = data?.byGroup.get(groupId) ?? [];
  // Chưa tải xong thì chưa biết nhóm có dự án hay không: không mời tạo dự án.
  const knownEmpty = !isPending && projects.length === 0;

  return (
    <section className="space-y-3 pt-2" aria-labelledby="team-projects-heading">
      <div className="flex items-center justify-between">
        <h2 id="team-projects-heading" className="text-base font-bold">
          Dự án
        </h2>
        {knownEmpty && isLeader ? (
          <Button type="button" size="sm" onClick={() => setCreateOpen(true)}>
            Tạo dự án
          </Button>
        ) : null}
      </div>

      {isPending ? (
        <p className="text-sm text-muted-foreground">Đang tải dự án của nhóm…</p>
      ) : knownEmpty ? (
        isLeader ? null : (
          <p className="text-sm text-muted-foreground">
            Nhóm chưa có dự án. Trưởng nhóm là người tạo dự án.
          </p>
        )
      ) : (
        <ul className="space-y-2">
          {projects.map((project) => (
            <li
              key={project.id}
              className="flex items-center justify-between rounded-lg border bg-card p-3"
            >
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono tracking-wide">
                  {project.identifier}
                </Badge>
                <span className="font-medium">{project.name}</span>
                {project.archived_at !== null ? (
                  <Badge variant="secondary">Đã lưu trữ</Badge>
                ) : null}
              </div>
              <Button asChild size="sm" variant="outline">
                <Link to={`/projects/${project.id}/info`}>Vào dự án</Link>
              </Button>
            </li>
          ))}
        </ul>
      )}

      <CreateProjectDialog
        groupId={groupId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </section>
  );
}
