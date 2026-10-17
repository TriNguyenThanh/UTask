import { extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge";
import {
  dropTargetForElements,
  monitorForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { useEffect, useRef, useState, type RefObject } from "react";

import { isIssueDrag } from "@/features/projects/dnd/useDraggableIssue";
import type { MoveDrop } from "@/features/projects/hooks/useIssueMover";
import type { Issue } from "@/features/projects/types";

export const SECTION_DROP = "section" as const;

/**
 * Makes a backlog section (one sprint, or the Product Backlog when `sprintId`
 * is null) a drop target, so an issue can be dropped on its header or on its
 * empty area as well as between its rows. True while an issue is over it.
 */
export function useSectionDropTarget(
  sectionRef: RefObject<HTMLElement | null>,
  sprintId: string | null,
  enabled: boolean,
): boolean {
  const [isOver, setIsOver] = useState(false);

  useEffect(() => {
    const section = sectionRef.current;
    if (!enabled || !section) return;
    return dropTargetForElements({
      element: section,
      canDrop: ({ source }) => isIssueDrag(source.data),
      getData: () => ({ type: SECTION_DROP, sprintId }),
      onDragEnter: () => setIsOver(true),
      onDragLeave: () => setIsOver(false),
      onDrop: () => setIsOver(false),
    });
  }, [sectionRef, sprintId, enabled]);

  return isOver;
}

/**
 * Turns a finished drag in the backlog into a move. Only the leader reaches
 * this (a member has nothing to drag here): the section decides the sprint,
 * the row under the pointer decides the position, an empty area means "last".
 */
export function useBacklogDropMonitor({
  enabled,
  issues,
  issuesIn,
  onMove,
}: Readonly<{
  enabled: boolean;
  issues: readonly Issue[];
  /** Rows currently shown in a section, in order. */
  issuesIn: (sprintId: string | null) => readonly Issue[];
  onMove: (drop: MoveDrop) => void;
}>) {
  const latest = useRef({ issues, issuesIn, onMove });
  latest.current = { issues, issuesIn, onMove };

  useEffect(() => {
    if (!enabled) return;
    return monitorForElements({
      canMonitor: ({ source }) => isIssueDrag(source.data),
      onDrop: ({ source, location }) => {
        const { issues: all, issuesIn: rowsIn, onMove: move } = latest.current;
        const targets = location.current.dropTargets;
        const section = targets.find((target) => target.data.type === SECTION_DROP);
        if (!section) return;
        const issue = all.find((candidate) => candidate.key === source.data.key);
        if (!issue) return;

        const sprintId = (section.data.sprintId as string | null) ?? null;
        const row = targets.find((target) => target.data.type === source.data.type);
        const edge = row ? extractClosestEdge(row.data) : null;

        move({
          issue,
          toSprintId: sprintId,
          destination: rowsIn(sprintId),
          target:
            row && (edge === "top" || edge === "bottom")
              ? { key: String(row.data.key), edge }
              : null,
        });
      },
    });
  }, [enabled]);
}
