import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ReasonDialog } from "@/components/feedback/ReasonDialog";
import { groupErrorMessage } from "@/features/courses/lib/groupErrors";
import type { CourseDetail, TeamMember } from "@/features/courses/types";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useLeaveGroup, useRemoveMember, useTransferLeader } from "@/lib/query/classroomHooks";

type Team = NonNullable<CourseDetail["team"]>;

type Pending =
  | { kind: "leave" }
  | { kind: "transfer" | "remove"; member: TeamMember };

const COPY = {
  leave: {
    title: "Rời nhóm",
    description: "Bạn sẽ rời khỏi nhóm này. Lý do được ghi vào lịch sử nhóm.",
    confirm: "Rời nhóm",
    success: "Bạn đã rời nhóm.",
  },
  transfer: {
    title: "Chuyển quyền Trưởng nhóm",
    description: "Thành viên được chọn sẽ trở thành Trưởng nhóm; bạn thành thành viên thường.",
    confirm: "Chuyển quyền",
    success: "Đã chuyển quyền Trưởng nhóm.",
  },
  remove: {
    title: "Loại thành viên khỏi nhóm",
    description: "Thành viên sẽ bị loại khỏi nhóm; lịch sử tham gia được giữ lại.",
    confirm: "Loại khỏi nhóm",
    success: "Đã loại thành viên khỏi nhóm.",
  },
} as const;

/**
 * Rời nhóm, chuyển Trưởng nhóm, loại thành viên: cùng một hộp thoại xin lý do. Chỉ
 * dùng được khi nhóm có `version` (chế độ Classroom thật). UI chỉ ẩn nút theo vai trò;
 * quyền do backend quyết định.
 */
export function useGroupCommands(team: Team | null): {
  enabled: boolean;
  isLeader: boolean;
  requestLeave: () => void;
  requestTransfer: (member: TeamMember) => void;
  requestRemove: (member: TeamMember) => void;
  dialog: ReactNode;
} {
  const groupId = team?.teamId ?? "";
  const leave = useLeaveGroup(groupId);
  const transfer = useTransferLeader(groupId);
  const remove = useRemoveMember(groupId);
  const [pending, setPending] = useState<Pending | null>(null);

  const version = team?.version;
  const enabled = version !== undefined;

  function confirm(reason: string) {
    const current = pending;
    setPending(null);
    if (!current || version === undefined) return;
    const base = { version, reason, idempotencyKey: newIdempotencyKey() };
    const handlers = {
      onSuccess: () => toast.success(COPY[current.kind].success),
      onError: (error: unknown) => toast.error(groupErrorMessage(error)),
    };
    if (current.kind === "leave") leave.mutate(base, handlers);
    else if (current.kind === "transfer") transfer.mutate({ ...base, userId: current.member.userId }, handlers);
    else remove.mutate({ ...base, userId: current.member.userId }, handlers);
  }

  const copy = COPY[pending?.kind ?? "leave"];
  const memberName = pending && pending.kind !== "leave" ? pending.member.displayName : "";

  return {
    enabled,
    isLeader: team?.isLeader ?? false,
    requestLeave: () => setPending({ kind: "leave" }),
    requestTransfer: (member) => setPending({ kind: "transfer", member }),
    requestRemove: (member) => setPending({ kind: "remove", member }),
    dialog: (
      <ReasonDialog
        open={pending !== null}
        title={memberName ? `${copy.title}: ${memberName}` : copy.title}
        description={copy.description}
        confirmLabel={copy.confirm}
        onCancel={() => setPending(null)}
        onConfirm={confirm}
      />
    ),
  };
}
