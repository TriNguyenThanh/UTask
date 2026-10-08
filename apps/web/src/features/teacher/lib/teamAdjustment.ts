/**
 * Advisory checks for changing team membership. They exist so the person sees
 * what a change would break BEFORE anything can be sent, not to replace the
 * backend: the server enforces class membership, size limits and the Leader
 * rule. No check here lets a limit be exceeded; a "warning" never means
 * "allowed". Nothing is ever deleted: history of membership and contribution
 * stays, and tasks already done by a student are not moved to another team.
 */

export interface AdjustMember {
  userId: string;
  name: string;
  role: "leader" | "member";
}

export interface AdjustTeam {
  teamId: string;
  name: string;
  members: readonly AdjustMember[];
  maxMembers: number;
}

export interface Verdict {
  /** Blocks the change. */
  errors: string[];
  /** The change is possible but has a consequence the person should read. */
  warnings: string[];
  ok: boolean;
}

function verdict(errors: string[], warnings: string[]): Verdict {
  return { errors, warnings, ok: errors.length === 0 };
}

export function leadersOf(team: AdjustTeam): AdjustMember[] {
  return team.members.filter((member) => member.role === "leader");
}

/**
 * Move a student between teams, or seat an unteamed student (`fromTeam` null).
 * When the student is the only Leader of the team they leave, a replacement
 * from the remaining members is required so the team never loses its Leader.
 */
export function validateMove(input: {
  studentId: string | null;
  fromTeam: AdjustTeam | null;
  toTeam: AdjustTeam | null;
  /** Leader to promote in the source team when the only Leader leaves. */
  replacementLeaderId: string | null;
  minMembers: number;
}): Verdict {
  const { studentId, fromTeam, toTeam, replacementLeaderId, minMembers } = input;
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!studentId) errors.push("Chọn sinh viên cần chuyển.");
  if (!toTeam) errors.push("Chọn nhóm đích.");
  if (!studentId || !toTeam) return verdict(errors, warnings);

  if (fromTeam && fromTeam.teamId === toTeam.teamId) {
    errors.push("Sinh viên đã ở nhóm này.");
  }
  if (toTeam.members.length >= toTeam.maxMembers) {
    errors.push(
      `${toTeam.name} đã đủ sĩ số tối đa (${toTeam.members.length}/${toTeam.maxMembers}). Giao diện không cho vượt sĩ số; ngoại lệ, nếu có, do nghiệp vụ quyết định ngoài màn này.`,
    );
  }

  if (fromTeam) {
    const remaining = fromTeam.members.filter((member) => member.userId !== studentId);
    const student = fromTeam.members.find((member) => member.userId === studentId);
    const onlyLeader =
      student?.role === "leader" && leadersOf(fromTeam).every((leader) => leader.userId === studentId);
    if (onlyLeader && remaining.length > 0) {
      if (!replacementLeaderId || !remaining.some((member) => member.userId === replacementLeaderId)) {
        errors.push(`${fromTeam.name} sẽ mất Leader. Chọn một thành viên còn lại làm Leader mới.`);
      }
    }
    if (remaining.length === 0) {
      warnings.push(`${fromTeam.name} sẽ không còn thành viên. Nhóm không bị xóa tự động.`);
    } else if (remaining.length < minMembers) {
      warnings.push(`${fromTeam.name} sẽ còn ${remaining.length} thành viên, ít hơn mức tối thiểu ${minMembers} của lớp.`);
    }
  }

  warnings.push(
    "Lịch sử thành viên và đóng góp cũ được giữ nguyên. Task đã làm không tự chuyển sang nhóm mới.",
  );
  return verdict(errors, warnings);
}

/** Make `newLeaderId` a Leader of `team`; the team must keep at least one Leader. */
export function validateLeaderChange(input: { team: AdjustTeam | null; newLeaderId: string | null }): Verdict {
  const { team, newLeaderId } = input;
  const errors: string[] = [];
  if (!team) errors.push("Chọn nhóm.");
  if (!newLeaderId) errors.push("Chọn thành viên làm Leader.");
  if (!team || !newLeaderId) return verdict(errors, []);

  const member = team.members.find((candidate) => candidate.userId === newLeaderId);
  if (!member) {
    errors.push("Chỉ có thể chỉ định Leader trong số thành viên của nhóm.");
  } else if (member.role === "leader") {
    errors.push(`${member.name} đã là Leader của ${team.name}.`);
  }
  return verdict(errors, [
    "Cách xử lý Leader hiện tại (giữ hay chuyển thành thành viên) chưa được nghiệp vụ chốt. Nhóm luôn phải còn ít nhất một Leader.",
  ]);
}

/** Create a team with one unteamed student as its first Leader. */
export function validateNewTeam(input: {
  name: string;
  leaderId: string | null;
  existingNames: readonly string[];
  minMembers: number;
}): Verdict {
  const { leaderId, existingNames, minMembers } = input;
  const name = input.name.trim();
  const errors: string[] = [];
  const warnings: string[] = [];
  if (name.length < 3) errors.push("Tên nhóm cần ít nhất 3 ký tự.");
  else if (name.length > 60) errors.push("Tên nhóm tối đa 60 ký tự.");
  else if (existingNames.some((existing) => existing.trim().toLowerCase() === name.toLowerCase())) {
    errors.push("Đã có nhóm trùng tên trong lớp.");
  }
  if (!leaderId) errors.push("Chọn sinh viên chưa có nhóm làm Leader đầu tiên; nhóm không được thiếu Leader.");
  if (minMembers > 1) {
    warnings.push(`Nhóm mới chỉ có 1 thành viên, ít hơn mức tối thiểu ${minMembers} của lớp.`);
  }
  return verdict(errors, warnings);
}
