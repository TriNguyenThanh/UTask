import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FilterSelect } from "@/features/teacher/components/FilterSelect";
import { DisabledAction } from "@/components/feedback/DisabledAction";
import { DiscardChangesConfirm } from "@/components/feedback/DiscardChangesConfirm";
import { classErrorMessage } from "@/features/teacher/lib/classErrors";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import {
  leadersOf,
  validateLeaderChange,
  validateMove,
  validateNewTeam,
  type AdjustTeam,
  type Verdict,
} from "@/features/teacher/lib/teamAdjustment";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import { useAdjustMember, useCreateTeam, useTransferTeamLeader } from "@/lib/query/teacherClassHooks";
import { useTeacherStudents, useTeacherTeams } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

export const TEAM_ADJUST_UNAVAILABLE =
  "Xác nhận không khả dụng với dữ liệu mẫu: không có thay đổi nào được áp dụng và không có gì được gửi đi.";

type Mode = "move" | "leader" | "create";

const MODES: { id: Mode; label: string }[] = [
  { id: "move", label: "Chuyển hoặc phân thành viên" },
  { id: "leader", label: "Chỉ định Leader" },
  { id: "create", label: "Tạo nhóm mới" },
];

const NONE = "";
/** Select value for "leave the team and join none"; real Classroom only. */
const REMOVE = "__remove__";

/** Tên kèm MSSV nếu có; hồ sơ thật có thể chưa có MSSV. */
function personLabel(person: Readonly<{ name: string; studentCode: string }>): string {
  return person.studentCode ? `${person.name} (${person.studentCode})` : person.name;
}

function VerdictView({ verdict }: Readonly<{ verdict: Verdict }>) {
  return (
    <div className="space-y-2" aria-live="polite">
      {verdict.errors.length > 0 ? (
        <ul role="alert" className="space-y-1">
          {verdict.errors.map((error) => (
            <li key={error} className="rounded bg-red-50 px-2 py-1 text-xs font-medium text-red-900">
              {error}
            </li>
          ))}
        </ul>
      ) : null}
      {verdict.warnings.length > 0 ? (
        <ul className="space-y-1">
          {verdict.warnings.map((warning) => (
            <li key={warning} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-950">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Body({ onDone, onDirtyChange }: Readonly<{ onDone: () => void; onDirtyChange: (dirty: boolean) => void }>) {
  const course = useTeacherCourseContext();
  const students = useTeacherStudents(course.courseId);
  const teams = useTeacherTeams(course.courseId);
  const [mode, setMode] = useState<Mode>("move");
  const [studentId, setStudentId] = useState(NONE);
  const [toTeamId, setToTeamId] = useState(NONE);
  const [replacementId, setReplacementId] = useState(NONE);
  const [leaderTeamId, setLeaderTeamId] = useState(NONE);
  const [newLeaderId, setNewLeaderId] = useState(NONE);
  const [teamName, setTeamName] = useState("");
  const [founderId, setFounderId] = useState(NONE);
  const [reason, setReason] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const adjust = useAdjustMember(course.courseId);
  const transfer = useTransferTeamLeader();
  const createTeam = useCreateTeam(course.courseId);
  const real = course.classroom !== undefined;
  const pending = adjust.isPending || transfer.isPending || createTeam.isPending;
  const reasonValid = reason.trim().length >= 3 && reason.trim().length <= 500;
  // Creating a team carries no reason: the backend does not take one.
  const reasonRequired = mode !== "create";

  const dirty =
    [studentId, toTeamId, replacementId, leaderTeamId, newLeaderId, founderId].some((v) => v !== NONE) ||
    teamName.trim() !== "" ||
    reason.trim() !== "";
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  if (students.isPending || teams.isPending) {
    return <output className="text-sm text-muted-foreground">Đang tải dữ liệu lớp…</output>;
  }
  if (students.isError || teams.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Không tải được dữ liệu lớp nên không thể kiểm tra việc điều chỉnh nhóm.
      </p>
    );
  }

  const adjustTeams: AdjustTeam[] = teams.data.teams.map((team) => ({
    teamId: team.teamId,
    name: team.name,
    maxMembers: team.maxMembers,
    members: team.members.map((member) => ({ userId: member.userId, name: member.name, role: member.role })),
  }));
  const teamById = (id: string) => adjustTeams.find((team) => team.teamId === id) ?? null;
  const roster = students.data.students;
  const unteamed = roster.filter((student) => student.team === null);

  const student = roster.find((candidate) => candidate.userId === studentId) ?? null;
  const fromTeam = student?.team ? teamById(student.team.teamId) : null;
  const unassign = real && toTeamId === REMOVE;
  const toTeam = unassign ? null : teamById(toTeamId);
  const needsReplacement =
    fromTeam !== null &&
    student !== null &&
    leadersOf(fromTeam).length === 1 &&
    leadersOf(fromTeam)[0].userId === student.userId &&
    fromTeam.members.length > 1;

  let verdict: Verdict;
  if (mode === "move") {
    verdict = validateMove({
      studentId: student?.userId ?? null,
      fromTeam,
      toTeam,
      replacementLeaderId: replacementId || null,
      minMembers: course.teamSize.min,
      unassign,
    });
  } else if (mode === "leader") {
    verdict = validateLeaderChange({
      team: teamById(leaderTeamId),
      newLeaderId: newLeaderId || null,
      leaderRule: real ? "swap" : "undecided",
    });
  } else {
    verdict = validateNewTeam({
      name: teamName,
      leaderId: founderId || null,
      existingNames: adjustTeams.map((team) => team.name),
      minMembers: course.teamSize.min,
    });
  }

  const teamOptions = [
    { value: NONE, label: "Chọn nhóm" },
    ...adjustTeams.map((team) => ({
      value: team.teamId,
      label: `${team.name} (${team.members.length}/${team.maxMembers})`,
    })),
  ];

  const teamRows = teams.data.teams;
  function apply() {
    const trimmed = reason.trim();
    setFailure(null);
    const handlers = {
      onSuccess: () => {
        toast.success("Đã cập nhật nhóm.");
        onDone();
      },
      onError: (error: unknown) => setFailure(classErrorMessage(error)),
    };
    if (mode === "move" && student) {
      adjust.mutate(
        {
          userId: student.userId,
          targetGroupId: unassign ? null : toTeamId,
          successorUserId: needsReplacement ? replacementId : undefined,
          reason: trimmed,
          idempotencyKey: newIdempotencyKey(),
        },
        handlers,
      );
    } else if (mode === "leader") {
      const version = teamRows.find((team) => team.teamId === leaderTeamId)?.version;
      if (version === undefined) return;
      transfer.mutate(
        { groupId: leaderTeamId, version, userId: newLeaderId, reason: trimmed, idempotencyKey: newIdempotencyKey() },
        handlers,
      );
    } else if (mode === "create") {
      createTeam.mutate(
        { name: teamName.trim(), leaderId: founderId, idempotencyKey: newIdempotencyKey() },
        handlers,
      );
    }
  }

  return (
    <div className="space-y-4">
      <fieldset aria-label="Loại điều chỉnh" className="m-0 flex min-w-0 flex-wrap gap-1.5 border-0 p-0">
        {MODES.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={mode === item.id}
            onClick={() => setMode(item.id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
              mode === item.id ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-secondary",
            )}
          >
            {item.label}
          </button>
        ))}
      </fieldset>

      {mode === "move" ? (
        <div className="space-y-3">
          <FilterSelect
            label="Sinh viên"
            value={studentId}
            onChange={(value) => {
              setStudentId(value);
              setReplacementId(NONE);
            }}
            options={[
              { value: NONE, label: "Chọn sinh viên" },
              ...roster.map((candidate) => ({
                value: candidate.userId,
                label: `${personLabel(candidate)} — ${candidate.team?.name ?? "chưa có nhóm"}`,
              })),
            ]}
          />
          <FilterSelect
            label="Nhóm đích"
            value={toTeamId}
            onChange={setToTeamId}
            options={real ? [...teamOptions, { value: REMOVE, label: "Không thuộc nhóm nào (bỏ khỏi nhóm)" }] : teamOptions}
          />
          {needsReplacement && fromTeam ? (
            <FilterSelect
              label={`Leader mới của ${fromTeam.name}`}
              value={replacementId}
              onChange={setReplacementId}
              options={[
                { value: NONE, label: "Chọn Leader mới" },
                ...fromTeam.members
                  .filter((member) => member.userId !== studentId)
                  .map((member) => ({ value: member.userId, label: member.name })),
              ]}
            />
          ) : null}
        </div>
      ) : null}

      {mode === "leader" ? (
        <div className="space-y-3">
          <FilterSelect
            label="Nhóm"
            value={leaderTeamId}
            onChange={(value) => {
              setLeaderTeamId(value);
              setNewLeaderId(NONE);
            }}
            options={teamOptions}
          />
          <FilterSelect
            label="Leader mới"
            value={newLeaderId}
            onChange={setNewLeaderId}
            options={[
              { value: NONE, label: "Chọn thành viên" },
              ...(teamById(leaderTeamId)?.members ?? []).map((member) => ({
                value: member.userId,
                label: `${member.name}${member.role === "leader" ? " (đang là Leader)" : ""}`,
              })),
            ]}
          />
        </div>
      ) : null}

      {mode === "create" ? (
        <div className="space-y-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="adjust-team-name" className="text-xs font-medium text-muted-foreground">
              Tên nhóm
            </label>
            <Input id="adjust-team-name" value={teamName} onChange={(event) => setTeamName(event.target.value)} />
          </div>
          <FilterSelect
            label="Leader đầu tiên (sinh viên chưa có nhóm)"
            value={founderId}
            onChange={setFounderId}
            options={[
              { value: NONE, label: "Chọn sinh viên" },
              ...unteamed.map((candidate) => ({
                value: candidate.userId,
                label: personLabel(candidate),
              })),
            ]}
          />
        </div>
      ) : null}

      <VerdictView verdict={verdict} />
      {real ? (
        <>
          {reasonRequired ? (
            <div className="space-y-1.5">
              <Label htmlFor="adjust-reason">Lý do</Label>
              <Textarea
                id="adjust-reason"
                rows={3}
                value={reason}
                aria-invalid={reason.length > 0 && !reasonValid ? true : undefined}
                onChange={(event) => setReason(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">Bắt buộc, 3–500 ký tự.</p>
            </div>
          ) : null}
          {failure ? (
            <p role="alert" className="rounded bg-red-50 px-2 py-1 text-xs font-medium text-red-900">
              {failure}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onDone}>
              Đóng
            </Button>
            <Button type="button" disabled={!verdict.ok || (reasonRequired && !reasonValid) || pending} onClick={apply}>
              {pending ? "Đang áp dụng…" : "Xác nhận thay đổi"}
            </Button>
          </DialogFooter>
        </>
      ) : (
        <>
          <output className="block text-sm font-medium">
            {verdict.ok ? "Đúng điều kiện cơ bản, nhưng dữ liệu mẫu không áp dụng thay đổi." : "Chưa đủ điều kiện để xác nhận."}
          </output>
          <p className="text-xs text-amber-900">{TEAM_ADJUST_UNAVAILABLE}</p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onDone}>
              Đóng
            </Button>
            <DisabledAction reason={TEAM_ADJUST_UNAVAILABLE} variant="default">
              Xác nhận thay đổi
            </DisabledAction>
          </DialogFooter>
        </>
      )}
    </div>
  );
}

/**
 * Change team membership: move/seat/remove a student, designate a Leader, or
 * create a team with an unteamed student as its Leader. It validates the
 * person's choices against the class data and shows the consequences. With
 * the real Classroom service the change is sent (a reason is required except
 * when creating a team); with demo data it applies nothing.
 */
export function TeamAdjustDialog() {
  const [open, setOpen] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const course = useTeacherCourseContext();
  const real = course.classroom !== undefined;

  function close() {
    setOpen(false);
    setDirty(false);
  }

  // Esc và nhấp ra ngoài dễ bấm nhầm nên hỏi lại khi đã nhập dở; "Hủy" đóng ngay.
  function askBeforeDiscard(event: Event) {
    if (!dirty) return;
    event.preventDefault();
    setConfirmDiscard(true);
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <DialogTrigger asChild>
          <Button type="button" variant="outline">
            Điều chỉnh nhóm
          </Button>
        </DialogTrigger>
        <DialogContent
          className="max-h-[90vh] overflow-y-auto"
          onInteractOutside={askBeforeDiscard}
          onEscapeKeyDown={askBeforeDiscard}
        >
          <DialogHeader>
            <DialogTitle>Điều chỉnh nhóm</DialogTitle>
            <DialogDescription>
              {real
                ? "Chọn thay đổi, xem điều kiện và hệ quả, nhập lý do rồi xác nhận. Lý do được ghi vào lịch sử nhóm."
                : "Chọn thay đổi để xem trước điều kiện và hệ quả. Với dữ liệu mẫu, thay đổi không được áp dụng."}
            </DialogDescription>
          </DialogHeader>
          {open ? <Body onDone={close} onDirtyChange={setDirty} /> : null}
        </DialogContent>
      </Dialog>
      <DiscardChangesConfirm
        open={confirmDiscard}
        onDiscard={() => {
          setConfirmDiscard(false);
          close();
        }}
        onKeepEditing={() => setConfirmDiscard(false)}
      />
    </>
  );
}
