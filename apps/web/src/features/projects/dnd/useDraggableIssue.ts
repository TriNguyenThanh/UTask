import { attachClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/attach-closest-edge";
import { extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import {
  draggable,
  dropTargetForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { useEffect, useState, type RefObject } from "react";

/** What every issue drag carries, so a drop target can tell what was dropped. */
export const ISSUE_DRAG = "issue" as const;

export function isIssueDrag(data: Record<string | symbol, unknown>): boolean {
  return data.type === ISSUE_DRAG && typeof data.key === "string";
}

/**
 * Makes one issue element a drag source (from its grip only) and a drop
 * target for other issues. Returns whether it is being dragged and, while
 * another issue hovers over it, the edge that issue would land on.
 *
 * `canDrag` false registers no drag source at all. `canReorder` false (a
 * member) reports no edge: dropping on the element then means "into its
 * list", never "above" or "below" it.
 */
export function useDraggableIssue({
  elementRef,
  handleRef,
  issueKey,
  canDrag,
  canReorder,
}: Readonly<{
  elementRef: RefObject<HTMLElement | null>;
  handleRef: RefObject<HTMLElement | null>;
  issueKey: string;
  canDrag: boolean;
  canReorder: boolean;
}>) {
  const [dragging, setDragging] = useState(false);
  const [closestEdge, setClosestEdge] = useState<"top" | "bottom" | null>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;
    const cleanups = [
      dropTargetForElements({
        element,
        canDrop: ({ source }) => isIssueDrag(source.data) && source.data.key !== issueKey,
        getData: ({ input, element: target }) => {
          const data = { type: ISSUE_DRAG, key: issueKey };
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
          getInitialData: () => ({ type: ISSUE_DRAG, key: issueKey }),
          onDragStart: () => setDragging(true),
          onDrop: () => setDragging(false),
        }),
      );
    }
    return combine(...cleanups);
  }, [canDrag, canReorder, elementRef, handleRef, issueKey]);

  return { dragging, closestEdge };
}
