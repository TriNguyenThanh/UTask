import { autoScrollForElements } from "@atlaskit/pragmatic-drag-and-drop-auto-scroll/element";
import { extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge/extract-closest-edge";
import {
  dropTargetForElements,
  monitorForElements,
} from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { useEffect, useRef, useState, type RefObject } from "react";

import { isIssueDrag } from "@/features/projects/dnd/useDraggableIssue";
import type { MoveDrop } from "@/features/projects/hooks/useIssueMover";
import type { Issue, IssueStatus } from "@/features/projects/types";

export const COLUMN_DROP = "column" as const;

/**
 * Makes a board column a drop target and reports whether an issue is being
 * dragged over it, so the whole column can be tinted. Also scrolls the
 * column's list when a card is dragged near its edge.
 */
export function useColumnDropTarget(
  columnRef: RefObject<HTMLElement | null>,
  listRef: RefObject<HTMLElement | null>,
  status: IssueStatus,
  stateId: string,
  enabled: boolean,
): boolean {
  const [isOver, setIsOver] = useState(false);

  useEffect(() => {
    const column = columnRef.current;
    const list = listRef.current;
    if (!enabled || !column) return;
    const cleanups = [
      dropTargetForElements({
        element: column,
        canDrop: ({ source }) => isIssueDrag(source.data),
        getData: () => ({ type: COLUMN_DROP, status, stateId }),
        onDragEnter: () => setIsOver(true),
        onDragLeave: () => setIsOver(false),
        onDrop: () => setIsOver(false),
      }),
    ];
    if (list) {
      cleanups.push(
        autoScrollForElements({
          element: list,
          canScroll: ({ source }) => isIssueDrag(source.data),
        }),
      );
    }
    return () => cleanups.forEach((cleanup) => cleanup());
  }, [columnRef, listRef, status, stateId, enabled]);

  return isOver;
}

/** Scrolls the board sideways when a card is dragged near its left or right edge. */
export function useBoardAutoScroll(board: HTMLElement | null, enabled: boolean) {
  // Takes the element itself (kept in state by the caller): the board is only
  // rendered once there is a running sprint, so it may appear after mount.
  useEffect(() => {
    if (!enabled || !board) return;
    return autoScrollForElements({
      element: board,
      canScroll: ({ source }) => isIssueDrag(source.data),
    });
  }, [board, enabled]);
}

/**
 * Turns a finished drag into a move. One monitor for the whole board: the
 * innermost drop target wins, so a card under the pointer decides the
 * position and the column decides the status. The latest issues and handler
 * are read through refs, so the monitor is registered once per `enabled`.
 */
export function useBoardDropMonitor({
  enabled,
  isLeader,
  issues,
  visibleIssuesFor,
  onMove,
}: Readonly<{
  enabled: boolean;
  isLeader: boolean;
  issues: readonly Issue[];
  visibleIssuesFor: (status: IssueStatus) => readonly Issue[];
  onMove: (drop: MoveDrop) => void;
}>) {
  const latest = useRef({ issues, isLeader, visibleIssuesFor, onMove });
  latest.current = { issues, isLeader, visibleIssuesFor, onMove };

  useEffect(() => {
    if (!enabled) return;
    return monitorForElements({
      canMonitor: ({ source }) => isIssueDrag(source.data),
      onDrop: ({ source, location }) => {
        const { issues: all, isLeader: leader, visibleIssuesFor: visible, onMove: move } =
          latest.current;
        const targets = location.current.dropTargets;
        const column = targets.find((target) => target.data.type === COLUMN_DROP);
        if (!column) return;
        const issue = all.find((candidate) => candidate.key === source.data.key);
        if (!issue) return;

        const status = column.data.status as IssueStatus;
        const stateId = column.data.stateId as string;
        const card = targets.find((target) => target.data.type === source.data.type);
        const edge = card ? extractClosestEdge(card.data) : null;

        move({
          issue,
          toStatus: status,
          toStateId: stateId,
          destination: visible(status),
          // Only the leader orders cards: dropping on a card means "next to it",
          // on the column background "at the end". A member's drop is status only.
          ...(leader
            ? {
                target:
                  card && (edge === "top" || edge === "bottom")
                    ? { key: String(card.data.key), edge }
                    : null,
              }
            : {}),
        });
      },
    });
  }, [enabled]);
}
