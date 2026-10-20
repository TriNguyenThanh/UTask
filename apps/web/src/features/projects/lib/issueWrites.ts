import type { MoveIntent } from "@/features/projects/lib/moveIntent";
import type { Issue } from "@/features/projects/types";

export interface MoveCommand {
  issue: Issue;
  intent: MoveIntent;
  /** Lý do đổi phạm vi Sprint; chỉ chế độ demo dùng. */
  reason?: string;
}

export interface BlockCommand {
  issue: Issue;
  blocked: boolean;
  reason?: string;
}

/** Cách `useIssueMover` ghi thay đổi: demo (MSW) hoặc Work thật. */
export interface IssueWrites {
  move: (command: MoveCommand) => void;
  setBlocked: (command: BlockCommand) => void;
}
