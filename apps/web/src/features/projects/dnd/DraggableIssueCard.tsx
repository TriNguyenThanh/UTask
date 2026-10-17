import { useRef, type ReactNode } from "react";

import { IssueCard } from "@/features/projects/components/IssueCard";
import { useDraggableIssue } from "@/features/projects/dnd/useDraggableIssue";
import type { Issue } from "@/features/projects/types";
import { cn } from "@/lib/utils";

/**
 * A board card that can be dragged and dropped on. Pressing anywhere on it
 * and moving drags it; a plain click still opens it, and the menu button is
 * excluded from dragging. The menu is the keyboard route.
 */
export function DraggableIssueCard({
  issue,
  onOpen,
  actions,
  highlighted,
  canDrag,
  canReorder,
}: Readonly<{
  issue: Issue;
  onOpen: (key: string) => void;
  actions: ReactNode;
  highlighted: boolean;
  canDrag: boolean;
  canReorder: boolean;
}>) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const { dragging, closestEdge } = useDraggableIssue({
    elementRef: wrapperRef,
    issueKey: issue.key,
    canDrag,
    canReorder,
  });

  return (
    <div
      ref={wrapperRef}
      className={cn(canDrag && "cursor-grab active:cursor-grabbing", dragging && "opacity-40")}
    >
      <IssueCard
        issue={issue}
        onOpen={onOpen}
        highlighted={highlighted}
        closestEdge={closestEdge}
        actions={actions}
      />
    </div>
  );
}
