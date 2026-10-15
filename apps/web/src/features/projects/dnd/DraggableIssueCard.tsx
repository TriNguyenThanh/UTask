import { GripVertical } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { IssueCard } from "@/features/projects/components/IssueCard";
import { useDraggableIssue } from "@/features/projects/dnd/useDraggableIssue";
import type { Issue } from "@/features/projects/types";
import { cn } from "@/lib/utils";

/** The grip a card or row is dragged by. Pointer-only: the menu is the keyboard route. */
export function DragGrip({ gripRef }: Readonly<{ gripRef: React.Ref<HTMLSpanElement> }>) {
  return (
    <span
      ref={gripRef}
      aria-hidden
      title="Kéo để di chuyển"
      className="-ml-1 flex size-5 shrink-0 cursor-grab items-center justify-center rounded text-muted-foreground hover:bg-muted active:cursor-grabbing"
    >
      <GripVertical className="size-4" />
    </span>
  );
}

/**
 * A board card that can be dragged and dropped on. Dragging starts only from
 * the grip, so the open button and the menu keep behaving like buttons.
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
  const gripRef = useRef<HTMLSpanElement | null>(null);
  const { dragging, closestEdge } = useDraggableIssue({
    elementRef: wrapperRef,
    handleRef: gripRef,
    issueKey: issue.key,
    canDrag,
    canReorder,
  });

  return (
    <div ref={wrapperRef} className={cn(dragging && "opacity-40")}>
      <IssueCard
        issue={issue}
        onOpen={onOpen}
        highlighted={highlighted}
        closestEdge={closestEdge}
        actions={actions}
        handle={canDrag ? <DragGrip gripRef={gripRef} /> : null}
      />
    </div>
  );
}
