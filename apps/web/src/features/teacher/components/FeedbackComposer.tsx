import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/AuthProvider";
import { DisabledAction } from "@/features/teacher/components/shared";
import { draftKey, useDraft } from "@/features/teacher/lib/drafts";

/** Interface limit only; the backend will own the real one. */
export const FEEDBACK_MAX_LENGTH = 2000;

export const FEEDBACK_UNAVAILABLE =
  "Gửi phản hồi chưa khả dụng: chưa có hợp đồng API bình luận/phản hồi. Nội dung bạn viết chỉ được giữ làm nháp trong tab này, chưa gửi cho ai và nhóm không nhận được thông báo.";

export function validateFeedback(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === "") return null; // empty is a state, not an error: nothing to validate yet
  if (trimmed.length > FEEDBACK_MAX_LENGTH) {
    return `Phản hồi dài ${trimmed.length} ký tự, vượt giới hạn ${FEEDBACK_MAX_LENGTH} của giao diện.`;
  }
  return null;
}

/**
 * A draft box for feedback to a team or on a task, with validation and a send
 * button that stays disabled until an API exists. Feedback is words only: it
 * never changes a task, a deadline or an assignee, and the box says so.
 */
export function FeedbackComposer({
  scope,
  label,
}: {
  /** What the draft belongs to, e.g. `team.<courseId>.<teamId>`; part of the storage key. */
  scope: string;
  label: string;
}) {
  const { user } = useAuth();
  const textareaId = useId();
  const errorId = useId();
  const [text, setText, clear] = useDraft(draftKey(user?.id ?? "anonymous", "feedback", scope));
  const error = validateFeedback(text);

  return (
    <div className="space-y-2">
      <label htmlFor={textareaId} className="text-sm font-medium">
        {label}
      </label>
      <Textarea
        id={textareaId}
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={4}
        aria-invalid={error !== null}
        aria-describedby={error ? errorId : undefined}
        placeholder="Viết nhận xét cho nhóm…"
      />
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span aria-live="polite">
          {text.trim() === ""
            ? "Chưa có nội dung."
            : `Đã lưu nháp trong tab này • ${text.trim().length}/${FEEDBACK_MAX_LENGTH} ký tự`}
        </span>
        <span>Phản hồi không tự đổi task, hạn chót hay người được giao.</span>
      </div>
      {error ? (
        <p id={errorId} role="alert" className="text-xs font-medium text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <DisabledAction reason={FEEDBACK_UNAVAILABLE} variant="default">
          Gửi phản hồi
        </DisabledAction>
        <Button type="button" variant="ghost" onClick={clear} disabled={text === ""}>
          Xóa nháp
        </Button>
      </div>
      <p className="text-xs text-amber-900">{FEEDBACK_UNAVAILABLE}</p>
    </div>
  );
}
