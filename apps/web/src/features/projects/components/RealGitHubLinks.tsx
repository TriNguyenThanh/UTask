import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { GitBranch, GitCommitHorizontal, GitPullRequest } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/idempotency";
import type { GitHubLinkTypeDto, TaskGitHubLinkDto } from "@/lib/api/work/dto";
import {
  useConfirmTaskGitHubLink,
  useCreateTaskGitHubLink,
  useDeleteTaskGitHubLink,
  useTaskGitHubLinks,
} from "@/lib/query/workGithubHooks";

const TYPE_LABEL: Record<GitHubLinkTypeDto, string> = {
  BRANCH: "Nhánh",
  COMMIT: "Commit",
  PULL_REQUEST: "Pull Request",
};

const TYPE_ICON = { BRANCH: GitBranch, COMMIT: GitCommitHorizontal, PULL_REQUEST: GitPullRequest } as const;

/** Chỉ lỗi của Work/Integration cần diễn giải; còn lại giữ thông điệp server. */
export function githubLinkErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 503 && error.code === "INTEGRATION_UNAVAILABLE") {
    return "Work chưa kết nối được Integration (chờ backend, B34).";
  }
  return error instanceof Error ? error.message : String(error);
}

/** Pull Request phải là số nguyên dương (bỏ `#` đầu), như `LinkInputSerializer`. */
export function isValidGitHubRef(type: GitHubLinkTypeDto, ref: string): boolean {
  const value = ref.trim();
  if (value === "" || value.length > 300) return false;
  if (type !== "PULL_REQUEST") return true;
  const digits = value.replace(/^#/, "");
  return /^[0-9]+$/.test(digits) && Number(digits) >= 1;
}

function linkTitle(link: TaskGitHubLinkDto): string {
  const text = link.github_title ?? link.github_ref_id;
  return link.link_type === "PULL_REQUEST" && link.github_title === null ? `#${link.github_ref_id}` : text;
}

function ErrorLine({ error, projectId }: { error: unknown; projectId: string }) {
  if (!error) return null;
  const needsRepository = error instanceof ApiError && error.code === "INVALID_OPERATION";
  return (
    <p role="alert" className="text-xs text-destructive">
      {githubLinkErrorMessage(error)}
      {needsRepository ? (
        <>
          {" "}
          <Link className="underline" to={`/projects/${projectId}/code`}>
            Mở tab Code
          </Link>
        </>
      ) : null}
    </p>
  );
}

function LinkRow({ taskId, projectId, link, editable }: { taskId: string; projectId: string; link: TaskGitHubLinkDto; editable: boolean }) {
  const confirm = useConfirmTaskGitHubLink(taskId);
  const remove = useDeleteTaskGitHubLink(taskId);
  const confirmKey = useRef<string | null>(null);
  const Icon = TYPE_ICON[link.link_type];
  const title = linkTitle(link);
  const pending = link.confirmation_status === "PENDING";

  function handleConfirm() {
    confirmKey.current ??= newIdempotencyKey();
    confirm.mutate(
      { linkId: link.id, idempotencyKey: confirmKey.current },
      { onSuccess: () => (confirmKey.current = null) },
    );
  }

  return (
    <li className="space-y-1 rounded-md border border-outline-subtle bg-card p-2 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span className="sr-only">{TYPE_LABEL[link.link_type]}</span>
        {link.github_url ? (
          <a className="min-w-0 truncate font-mono text-primary underline" href={link.github_url} target="_blank" rel="noreferrer">
            {title}
          </a>
        ) : (
          <span className="min-w-0 truncate font-mono">{title}</span>
        )}
        {link.github_status ? <span className="text-muted-foreground">{link.github_status}</span> : null}
        <Badge variant={pending ? "secondary" : "default"}>{pending ? "Chờ xác nhận" : "Đã xác nhận"}</Badge>
      </div>
      {editable ? (
        <div className="flex flex-wrap gap-1.5">
          {pending && link.is_verified ? (
            <Button type="button" size="sm" variant="outline" disabled={confirm.isPending} onClick={handleConfirm} aria-label={`Xác nhận ${title}`}>
              Xác nhận
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={remove.isPending}
            onClick={() => remove.mutate({ linkId: link.id })}
            aria-label={`Xóa liên kết ${title}`}
          >
            Xóa
          </Button>
        </div>
      ) : null}
      <ErrorLine error={confirm.error ?? remove.error} projectId={projectId} />
    </li>
  );
}

function AddLinkForm({ taskId, projectId }: { taskId: string; projectId: string }) {
  const create = useCreateTaskGitHubLink(taskId);
  const [type, setType] = useState<GitHubLinkTypeDto>("BRANCH");
  const [ref, setRef] = useState("");
  const [invalid, setInvalid] = useState(false);
  /** Cùng input → cùng key (thử lại không tạo trùng); input đổi hoặc thành công → key mới. */
  const attempt = useRef<{ signature: string; key: string } | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!isValidGitHubRef(type, ref)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    const value = ref.trim();
    const signature = `${type}:${value}`;
    if (attempt.current?.signature !== signature) attempt.current = { signature, key: newIdempotencyKey() };
    create.mutate(
      { linkType: type, githubRefId: value, idempotencyKey: attempt.current.key },
      {
        onSuccess: () => {
          attempt.current = null;
          setRef("");
        },
      },
    );
  }

  return (
    <form className="space-y-1.5" onSubmit={submit}>
      <div className="flex flex-wrap items-center gap-1.5">
        <select
          aria-label="Loại liên kết GitHub"
          className="h-8 rounded-md border bg-background px-2 text-xs"
          value={type}
          onChange={(event) => setType(event.target.value as GitHubLinkTypeDto)}
        >
          {(Object.keys(TYPE_LABEL) as GitHubLinkTypeDto[]).map((value) => (
            <option key={value} value={value}>
              {TYPE_LABEL[value]}
            </option>
          ))}
        </select>
        <Input
          className="h-8 w-40 text-xs"
          aria-label="Mã tham chiếu GitHub"
          placeholder={type === "PULL_REQUEST" ? "Số PR, ví dụ 12" : type === "COMMIT" ? "SHA commit" : "Tên nhánh"}
          value={ref}
          onChange={(event) => setRef(event.target.value)}
        />
        <Button type="submit" size="sm" disabled={create.isPending}>
          Thêm liên kết
        </Button>
      </div>
      {invalid ? (
        <p role="alert" className="text-xs text-destructive">
          {type === "PULL_REQUEST" ? "Mã Pull Request phải là số nguyên dương." : "Nhập mã tham chiếu GitHub."}
        </p>
      ) : null}
      <ErrorLine error={create.error} projectId={projectId} />
    </form>
  );
}

/** Nội dung của khối "GitHub Development" trong panel khi chạy Work thật. */
export function RealGitHubLinks({ taskId, projectId, editable }: { taskId: string; projectId: string; editable: boolean }) {
  const query = useTaskGitHubLinks(taskId);
  const links = (query.data ?? []).filter((link) => link.deleted_at === null);

  return (
    <div className="space-y-2.5">
      {query.isPending ? (
        <p role="status" className="text-xs text-muted-foreground">
          Đang tải liên kết GitHub…
        </p>
      ) : query.isError ? (
        <ErrorLine error={query.error} projectId={projectId} />
      ) : links.length === 0 ? (
        <p className="text-xs text-muted-foreground">Chưa có liên kết mã nguồn.</p>
      ) : (
        <ul className="space-y-1.5" aria-label="Liên kết GitHub">
          {links.map((link) => (
            <LinkRow key={link.id} taskId={taskId} projectId={projectId} link={link} editable={editable} />
          ))}
        </ul>
      )}
      {editable ? <AddLinkForm taskId={taskId} projectId={projectId} /> : null}
    </div>
  );
}
