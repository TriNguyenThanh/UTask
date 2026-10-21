import type { CommentTarget } from "@/lib/api/work/endpoints.collab";
import { Download, History, MessageSquare, Paperclip, Trash2 } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { describeActivity, type ActivityLookup } from "@/features/projects/lib/activity";
import { formatBytes, validateAttachmentFile } from "@/features/projects/lib/attachmentRules";
import { formatDateTime, initialsOf, personName, validateCommentText } from "@/features/projects/lib/comments";
import { collabWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { CommentDto } from "@/lib/api/work/dto";
import {
  useAttachmentDownload,
  useComments,
  useCreateComment,
  useDeleteAttachment,
  useDeleteComment,
  usePatchComment,
  useTaskActivities,
  useTaskAttachments,
  useUploadAttachment,
} from "@/lib/query/workCollabHooks";
import { cn } from "@/lib/utils";

export interface CollabActor {
  userId: string;
  /** Leader xóa được mọi bình luận. */
  isLeader: boolean;
  /** Thành viên và giảng viên đều bình luận được; dự án lưu trữ thì không. */
  canComment: boolean;
  /** Tệp đính kèm chỉ thành viên ghi được (không phải giảng viên, không phải dự án lưu trữ). */
  canUpload: boolean;
}

type Person = { userId: string; name: string };

const SECTION = "space-y-3 border-t border-outline-subtle pt-4";
const HEADING = "flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider";

/* ------------------------------------------------------------------ */
/* Bình luận                                                           */
/* ------------------------------------------------------------------ */

function MentionPicker({
  people,
  selected,
  onToggle,
}: Readonly<{ people: readonly Person[]; selected: ReadonlySet<string>; onToggle: (userId: string) => void }>) {
  if (people.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Nhắc đến">
      <span className="text-[11px] text-muted-foreground">Nhắc đến:</span>
      {people.map((person) => (
        <button
          key={person.userId}
          type="button"
          aria-pressed={selected.has(person.userId)}
          aria-label={`Nhắc ${person.name}`}
          onClick={() => onToggle(person.userId)}
          className={cn(
            "rounded-full border px-2 py-0.5 text-[11px]",
            selected.has(person.userId) ? "border-primary bg-primary/10 text-primary" : "border-outline-subtle text-muted-foreground",
          )}
        >
          @{person.name}
        </button>
      ))}
    </div>
  );
}

function toggled(set: ReadonlySet<string>, userId: string): Set<string> {
  const next = new Set(set);
  if (next.has(userId)) next.delete(userId);
  else next.add(userId);
  return next;
}

function CommentComposer({
  target,
  people,
  actor,
}: Readonly<{ target: CommentTarget; people: readonly Person[]; actor: CollabActor }>) {
  const fieldId = useId();
  const [text, setText] = useState("");
  const [mentions, setMentions] = useState<ReadonlySet<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const create = useCreateComment(target);

  function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = validateCommentText(text);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    create.mutate(
      { content: text.trim(), mentionedUserIds: [...mentions] },
      {
        onSuccess: () => {
          setText("");
          setMentions(new Set());
        },
        onError: (failure) => setError(collabWriteErrorMessage(failure)),
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-2" noValidate>
      <label htmlFor={fieldId} className="sr-only">
        Viết bình luận
      </label>
      <Textarea
        id={fieldId}
        value={text}
        rows={3}
        disabled={create.isPending}
        placeholder="Viết bình luận…"
        aria-invalid={error !== null}
        onChange={(event) => {
          setText(event.target.value);
          setError(null);
        }}
      />
      <MentionPicker
        people={people.filter((person) => person.userId !== actor.userId)}
        selected={mentions}
        onToggle={(userId) => setMentions((current) => toggled(current, userId))}
      />
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="sm" disabled={create.isPending}>
        {create.isPending ? "Đang gửi…" : "Gửi bình luận"}
      </Button>
    </form>
  );
}

function CommentItem({
  comment,
  people,
  actor,
}: Readonly<{ comment: CommentDto; people: readonly Person[]; actor: CollabActor }>) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.content_stripped);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const patch = usePatchComment();
  const remove = useDeleteComment();
  const name = personName(comment.user_id, people, comment.display_name);
  const isMine = comment.user_id === actor.userId;
  const mentioned = comment.mentioned_user_ids.map((userId) => personName(userId, people));

  function save() {
    const invalid = validateCommentText(draft);
    if (invalid) {
      setError(invalid);
      return;
    }
    patch.mutate(
      { commentId: comment.id, content: draft.trim(), mentionedUserIds: comment.mentioned_user_ids },
      {
        onSuccess: () => {
          setEditing(false);
          setError(null);
        },
        onError: (failure) => setError(collabWriteErrorMessage(failure)),
      },
    );
  }

  return (
    <li className="rounded-lg border border-outline-subtle bg-muted/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-bold text-primary">
            {initialsOf(name)}
          </span>
          <span className="truncate text-xs font-bold">{name}</span>
          {comment.is_teacher_feedback ? (
            <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
              Phản hồi giảng viên
            </span>
          ) : null}
        </div>
        <time dateTime={comment.created_at} className="shrink-0 text-[11px] text-muted-foreground">
          {formatDateTime(comment.created_at)}
        </time>
      </div>

      {editing ? (
        <div className="mt-2 space-y-2">
          <Textarea
            aria-label="Nội dung bình luận"
            value={draft}
            rows={3}
            disabled={patch.isPending}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(null);
            }}
          />
          {error ? (
            <p role="alert" className="text-xs font-medium text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button size="sm" onClick={save} disabled={patch.isPending}>
              Lưu
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={patch.isPending}
              onClick={() => {
                setEditing(false);
                setDraft(comment.content_stripped);
                setError(null);
              }}
            >
              Hủy
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{comment.content_stripped}</p>
          {mentioned.length > 0 ? (
            <p className="mt-1 text-[11px] text-muted-foreground">Nhắc đến: {mentioned.map((n) => `@${n}`).join(", ")}</p>
          ) : null}
          {error ? (
            <p role="alert" className="mt-1 text-xs font-medium text-destructive">
              {error}
            </p>
          ) : null}
          {actor.canComment && (isMine || actor.isLeader) ? (
            <div className="mt-2 flex gap-1">
              {isMine ? (
                <Button size="sm" variant="ghost" onClick={() => setEditing(true)} aria-label="Sửa bình luận">
                  Sửa
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)} aria-label="Xóa bình luận">
                Xóa
              </Button>
            </div>
          ) : null}
        </>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Xóa bình luận?"
        description="Bình luận sẽ biến mất khỏi danh sách."
        confirmLabel="Xóa bình luận"
        destructive
        pending={remove.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() =>
          remove.mutate(comment.id, {
            onSuccess: () => setConfirmDelete(false),
            onError: (failure) => {
              setConfirmDelete(false);
              setError(collabWriteErrorMessage(failure));
            },
          })
        }
      />
    </li>
  );
}

/** Bình luận thật của một task: danh sách, soạn, sửa, xóa. Giảng viên cũng bình luận được (server tự gắn huy hiệu phản hồi). */
export function RealComments({
  target,
  actor,
  people,
  title = "Bình luận (Comments)",
}: Readonly<{ target: CommentTarget; actor: CollabActor; people: readonly Person[]; title?: string }>) {
  const query = useComments(target);
  const rows = [...(query.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <section className={SECTION}>
      <h3 className={HEADING}>
        <MessageSquare className="size-4" aria-hidden />
        {title}
      </h3>
      {actor.canComment ? <CommentComposer target={target} people={people} actor={actor} /> : null}
      {query.isPending ? <p className="text-xs text-muted-foreground">Đang tải bình luận…</p> : null}
      {query.error ? <p role="alert" className="text-xs text-destructive">Không tải được bình luận. Đóng và thử lại.</p> : null}
      {query.data && rows.length === 0 ? <p className="text-xs text-muted-foreground">Chưa có bình luận nào.</p> : null}
      {rows.length > 0 ? (
        <ul className="space-y-2.5">
          {rows.map((comment) => (
            <CommentItem key={comment.id} comment={comment} people={people} actor={actor} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Lịch sử                                                             */
/* ------------------------------------------------------------------ */

export function RealActivity({
  taskId,
  people,
  lookup,
}: Readonly<{ taskId: string; people: readonly Person[]; lookup?: ActivityLookup }>) {
  const query = useTaskActivities(taskId);
  const rows = [...(query.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <section className={SECTION}>
      <h3 className={HEADING}>
        <History className="size-4" aria-hidden />
        Lịch sử (History)
      </h3>
      {query.isPending ? <p className="text-xs text-muted-foreground">Đang tải lịch sử…</p> : null}
      {query.error ? <p role="alert" className="text-xs text-destructive">Không tải được lịch sử.</p> : null}
      {query.data && rows.length === 0 ? <p className="text-xs text-muted-foreground">Chưa có hoạt động nào.</p> : null}
      {rows.length > 0 ? (
        <ul className="space-y-2">
          {rows.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-3 rounded-md border border-outline-subtle bg-card px-3 py-2">
              <span className="text-xs">
                <span className="font-semibold">{personName(entry.actor_user_id, people)}</span>{" "}
                <span className="text-muted-foreground">{describeActivity(entry, lookup)}</span>
              </span>
              <time dateTime={entry.created_at} className="shrink-0 text-[11px] text-muted-foreground">
                {formatDateTime(entry.created_at)}
              </time>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Tệp đính kèm                                                        */
/* ------------------------------------------------------------------ */

export function RealAttachments({ taskId, actor }: Readonly<{ taskId: string; actor: CollabActor }>) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const query = useTaskAttachments(taskId);
  const upload = useUploadAttachment(taskId);
  const remove = useDeleteAttachment(taskId);
  const download = useAttachmentDownload(taskId);

  function choose(file: File | undefined) {
    if (!file) return;
    const invalid = validateAttachmentFile(file);
    if (inputRef.current) inputRef.current.value = "";
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    upload.mutate(file, {
      onSuccess: () => toast.success("Đã đính kèm tệp."),
      onError: (failure) => setError(collabWriteErrorMessage(failure)),
    });
  }

  function open(attachmentId: string) {
    download.mutate(attachmentId, {
      onSuccess: (url) => window.open(url, "_blank", "noopener,noreferrer"),
      onError: (failure) => setError(collabWriteErrorMessage(failure)),
    });
  }

  const rows = query.data ?? [];
  const target = rows.find((row) => row.id === removing);

  return (
    <section className={SECTION}>
      <h3 className={HEADING}>
        <Paperclip className="size-4" aria-hidden />
        Tệp đính kèm
      </h3>
      {actor.canUpload ? (
        <div className="space-y-1">
          <input
            ref={inputRef}
            type="file"
            aria-label="Chọn tệp đính kèm"
            disabled={upload.isPending}
            onChange={(event) => choose(event.target.files?.[0])}
            className="block w-full text-xs file:mr-3 file:rounded-md file:border file:border-outline-subtle file:bg-card file:px-3 file:py-1.5 file:text-xs"
          />
          <p className="text-[11px] text-muted-foreground">
            Ảnh JPEG/PNG/WebP, PDF, ZIP, văn bản thuần hoặc JSON, tối đa 25 MB.
          </p>
          {upload.isPending ? <p role="status" className="text-xs text-muted-foreground">Đang tải lên…</p> : null}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
      {query.isPending ? <p className="text-xs text-muted-foreground">Đang tải danh sách tệp…</p> : null}
      {query.error ? <p role="alert" className="text-xs text-destructive">Không tải được danh sách tệp.</p> : null}
      {query.data && rows.length === 0 ? <p className="text-xs text-muted-foreground">Chưa có tệp đính kèm.</p> : null}
      {rows.length > 0 ? (
        <ul className="divide-y divide-outline-subtle/60 overflow-hidden rounded-lg border border-outline-subtle bg-card text-xs">
          {rows.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-2 p-2.5">
              <span className="min-w-0 truncate">
                <span className="font-medium">{row.file_name}</span>{" "}
                <span className="text-muted-foreground">({formatBytes(row.file_size)})</span>
              </span>
              <span className="flex shrink-0 gap-1">
                <Button size="icon-sm" variant="ghost" aria-label={`Tải ${row.file_name}`} onClick={() => open(row.id)} disabled={download.isPending}>
                  <Download aria-hidden />
                </Button>
                {actor.canUpload ? (
                  <Button size="icon-sm" variant="ghost" aria-label={`Xóa ${row.file_name}`} onClick={() => setRemoving(row.id)}>
                    <Trash2 aria-hidden />
                  </Button>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <ConfirmDialog
        open={target !== undefined}
        title="Xóa tệp đính kèm?"
        description={target ? `Tệp "${target.file_name}" sẽ bị gỡ khỏi issue.` : ""}
        confirmLabel="Xóa tệp"
        destructive
        pending={remove.isPending}
        onCancel={() => setRemoving(null)}
        onConfirm={() =>
          remove.mutate(removing ?? "", {
            onSuccess: () => setRemoving(null),
            onError: (failure) => {
              setRemoving(null);
              setError(collabWriteErrorMessage(failure));
            },
          })
        }
      />
    </section>
  );
}

/** Ba khối cộng tác của một task thật, theo đúng thứ tự `IssuePanel` đặt chúng. `key` theo task để không giữ bản nháp sang issue khác. */
export function collabSlots(taskId: string, actor: CollabActor, people: readonly Person[], lookup?: ActivityLookup) {
  return {
    commentsSlot: <RealComments key={taskId} target={{ taskId }} actor={actor} people={people} />,
    attachmentsSlot: <RealAttachments key={taskId} taskId={taskId} actor={actor} />,
    historySlot: <RealActivity key={taskId} taskId={taskId} people={people} lookup={lookup} />,
  };
}
