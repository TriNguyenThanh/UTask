import { attachClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/attach-closest-edge";
import { extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import {
  draggable,
  dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { GripVertical } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { IssueCard } from "@/features/projects/components/IssueCard";
import type { Issue } from "@/features/projects/types";
import { cn } from "@/lib/utils";

/** What every issue drag carries, so a drop target can tell what was dropped. */
export const ISSUE_DRAG = "issue" as const;

export interface IssueDragData {
  type: typeof ISSUE_DRAG;
  key: string;
}

export function isIssueDrag(data: Record<string | symbol, unknown>): data is IssueDragData & Record<string | symbol, unknown> {
  return data.type === ISSUE_DRAG && typeof data.key === "string";
}

/**
 * A board card that can be dragged and dropped on. Dragging starts only from
 * the grip, so the open button and the menu keep behaving like buttons.
 *
 * `canDrag` is false for a card the viewer may not move; then no listener is
 * registered and no grip is drawn. `canReorder` decides whether another card
 * dropped here reports "above" or "below" (the leader) or only "into this
 * column" (a member).
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
  const handleRef = useRef<HTMLSpanElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [closestEdge, setClosestEdge] = useState<"top" | "bottom" | null>(null);

  useEffect(() => {
    const element = wrapperRef.current;
    if (!element) return;
    const cleanups = [
      dropTargetForElements({
        element,
        canDrop: ({ source }) => isIssueDrag(source.data) && source.data.key !== issue.key,
        getData: ({ input, element: target }) => {
          const data = { type: ISSUE_DRAG, key: issue.key };
          return canReorder
            ? attachClosestEdge(data, { element: target, input, allowedEdges: ["top", "bottom"] })
            : data;
        },
        onDrag: ({ self }) => {
          const edge = extractClosestEdge(self.data);
          setClosestEdge(edge === "top" || edge === "bottom" ? edge : null);
        },
        onDragLeave: () => setClosestEdge(null),
        onDrop: () => setClosestEdge(null),
      }),
    ];
    if (canDrag) {
      cleanups.push(
        draggable({
          element,
          dragHandle: handleRef.current ?? undefined,
          getInitialData: () => ({ type: ISSUE_DRAG, key: issue.key }),
          onDragStart: () => setDragging(true),
          onDrop: () => setDragging(false),
        }),
      );
    }
    return combine(...cleanups);
  }, [canDrag, canReorder, issue.key]);

  return (
    <div ref={wrapperRef} className={cn(dragging && "opacity-40")}>
      <IssueCard
        issue={issue}
        onOpen={onOpen}
        highlighted={highlighted}
        closestEdge={closestEdge}
        actions={actions}
        handle={
          canDrag ? (
            <span
              ref={handleRef}
              aria-hidden
              title="Kéo để di chuyển"
              className="-ml-1 flex size-5 shrink-0 cursor-grab items-center justify-center rounded text-muted-foreground hover:bg-muted active:cursor-grabbing"
            >
              <GripVertical className="size-4" />
            </span>
          ) : null
        }
      />
    </div>
  );
}
