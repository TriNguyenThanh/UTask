import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ProjectMemberDto } from "@/lib/api/work/dto";
import { useDeclareGitHubUsername, useRequestGitHubVerification } from "@/lib/query/workGithubHooks";

/** Bỏ `@` đầu và khoảng trắng; server mới là nơi kiểm định dạng. */
export function normalizeGitHubUsername(text: string): string {
  return text.trim().replace(/^@/, "");
}

function VerificationBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge variant="outline" className="border-emerald-200 bg-emerald-100 text-emerald-800">
      Đã xác minh
    </Badge>
  ) : (
    <Badge variant="secondary">Chưa xác minh</Badge>
  );
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Đã xảy ra lỗi. Vui lòng thử lại.";
}

/** Ô nhập của chính mình: PATCH username. Lỗi hiện nguyên message của server. */
function OwnGitHubForm({ projectId, member }: { projectId: string; member: ProjectMemberDto }) {
  const declare = useDeclareGitHubUsername(projectId);
  const saved = member.github_username ?? "";
  const [text, setText] = useState(saved);
  const [syncedWith, setSyncedWith] = useState(saved);
  if (saved !== syncedWith) {
    setSyncedWith(saved);
    setText(saved);
  }
  const value = normalizeGitHubUsername(text);
  const changed = value !== "" && value !== saved;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (changed) declare.mutate({ userId: member.user_id, githubUsername: value });
  }

  return (
    <form className="flex flex-wrap items-center gap-2" onSubmit={submit}>
      <Input
        value={text}
        className="h-8 w-40"
        placeholder="username GitHub"
        aria-label="Username GitHub của bạn"
        disabled={declare.isPending}
        onChange={(event) => setText(event.target.value)}
      />
      {changed ? (
        <Button type="submit" size="sm" disabled={declare.isPending}>
          Lưu
        </Button>
      ) : null}
      {saved ? <VerificationBadge verified={member.is_github_verified} /> : null}
      {declare.error ? <span className="w-full text-xs text-destructive">{errorText(declare.error)}</span> : null}
    </form>
  );
}

function VerificationRequestButton({ projectId, member }: { projectId: string; member: ProjectMemberDto }) {
  const request = useRequestGitHubVerification(projectId);
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={request.isPending || request.isSuccess}
        onClick={() => request.mutate({ userId: member.user_id })}
      >
        {request.isSuccess ? "Đã gửi yêu cầu" : "Yêu cầu xác minh"}
      </Button>
      {request.error ? <span className="w-full text-xs text-destructive">{errorText(request.error)}</span> : null}
    </>
  );
}

export function MemberGitHubCell({
  projectId,
  member,
  isSelf,
  canRequestVerification,
}: {
  projectId: string;
  member: ProjectMemberDto;
  isSelf: boolean;
  /** Leader của dự án đang xem hàng của người khác. */
  canRequestVerification: boolean;
}) {
  if (isSelf) {
    return <OwnGitHubForm projectId={projectId} member={member} />;
  }
  if (!member.github_username) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span>@{member.github_username}</span>
      <VerificationBadge verified={member.is_github_verified} />
      {canRequestVerification && !member.is_github_verified ? (
        <VerificationRequestButton projectId={projectId} member={member} />
      ) : null}
    </div>
  );
}
