import { useState } from "react";

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
import { FilterSelect } from "@/features/teacher/components/FilterSelect";
import { DisabledAction } from "@/features/teacher/components/shared";
import { useTeacherCourseContext } from "@/features/teacher/courseContext";
import {
  leadersOf,
  validateLeaderChange,
  validateMove,
  validateNewTeam,
  type AdjustTeam,
  type Verdict,
} from "@/features/teacher/lib/teamAdjustment";
import { useTeacherStudents, useTeacherTeams } from "@/lib/query/teacherFlowHooks";
import { cn } from "@/lib/utils";

export const TEAM_ADJUST_UNAVAILABLE =
  "Xác nhận chưa khả dụng: chưa có hợp đồng API đổi thành viên/Leader và chưa chốt chính sách sĩ số, Leader thay thế, quyền xem lịch sử sau khi chuyển nhóm. Chưa có gì được thay đổi.";

type Mode = "move" | "leader" | "create";

const MODES: { id: Mode; label: string }[] = [
  { id: "move", label: "Chuyển hoặc phân thành viên" },
  { id: "leader", label: "Chỉ định Leader" },
  { id: "create", label: "Tạo nhóm mới" },
];

const NONE = "";

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

function Body({ onDone }: Readonly<{ onDone: () => void }>) {
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
  const toTeam = teamById(toTeamId);
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
    });
  } else if (mode === "leader") {
    verdict = validateLeaderChange({ team: teamById(leaderTeamId), newLeaderId: newLeaderId || null });
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
                label: `${candidate.name} (${candidate.studentCode}) — ${candidate.team?.name ?? "chưa có nhóm"}`,
              })),
            ]}
          />
          <FilterSelect label="Nhóm đích" value={toTeamId} onChange={setToTeamId} options={teamOptions} />
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
                label: `${candidate.name} (${candidate.studentCode})`,
              })),
            ]}
          />
        </div>
      ) : null}

      <VerdictView verdict={verdict} />
      <output className="block text-sm font-medium">
        {verdict.ok ? "Đúng điều kiện cơ bản, nhưng việc xác nhận vẫn chưa khả dụng." : "Chưa đủ điều kiện để xác nhận."}
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
    </div>
  );
}

/**
 * Change team membership: move/seat a student, designate a Leader, create a
 * team. It validates the person's choices against the class data and shows
 * the consequences; it cannot apply anything, and says so.
 */
export function TeamAdjustDialog() {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          Điều chỉnh nhóm
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Điều chỉnh nhóm</DialogTitle>
          <DialogDescription>
            Chọn thay đổi để xem trước điều kiện và hệ quả. Hiện chưa thể áp dụng.
          </DialogDescription>
        </DialogHeader>
        {open ? <Body onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
