import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AiContextNotes } from "@/features/projects/components/ai/AiContextNotes";
import { AiProposalList } from "@/features/projects/components/ai/AiProposalList";
import { AiRunStatus } from "@/features/projects/components/ai/AiRunStatus";
import {
  markCreated,
  pendingItems,
  setSelected,
  setTitle,
  toDraft,
  type DraftItem,
} from "@/features/projects/lib/aiDraft";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { AiContextDto, AiRequestBody } from "@/lib/api/ai/dto";
import { useAiRequest, useApplyProposal } from "@/lib/query/aiHooks";

interface Selection<S> {
  items: S[];
  warnings: string[];
}

interface Draft<S> {
  items: DraftItem<S>[];
  warnings: string[];
  context: AiContextDto | null;
}

export interface AiProposalDialogProps<R, S extends { title: string }> {
  triggerLabel: string;
  triggerSize: "xs" | "sm";
  title: string;
  description: string;
  /** Các ô nhập của bước 1. State của chúng do bên gọi giữ. */
  form: ReactNode;
  /** Gọi mỗi lần mở: bên gọi đặt lại/điền sẵn các ô nhập. */
  onOpen: () => void;
  canGenerate: boolean;
  buildBody: () => AiRequestBody;
  select: (result: R) => Selection<S>;
  renderDetails: (source: S) => ReactNode;
  /** Ghi chú cố định ở bước xem gợi ý (ví dụ quyền của người không phải Leader). */
  reviewNote?: ReactNode;
  emptyMessage: string;
  /** Danh từ của mục được tạo, dùng trong nút và thông báo: "nhiệm vụ con", "issue". */
  noun: string;
  successMessage: (created: number) => string;
  create: (source: S, title: string, idempotencyKey: string) => Promise<unknown>;
}

interface ApplyInput<S> {
  source: S;
  title: string;
}

/**
 * Quy trình chung: nhập → AI gợi ý → chọn/sửa tiêu đề → Accept tạo thật.
 * Đóng hộp là bỏ gợi ý; hủy chỉ dừng chờ ở trình duyệt (request vẫn chạy ở server).
 */
export function AiProposalDialog<R, S extends { title: string }>(props: Readonly<AiProposalDialogProps<R, S>>) {
  const { select, create } = props;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Draft<S> | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const ai = useAiRequest<R>();
  const apply = useApplyProposal<ApplyInput<S>>();
  const controller = useRef<AbortController | null>(null);
  const { reset: resetAi } = ai;

  const abort = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
  }, []);

  useEffect(() => abort, [abort]);

  function show(next: boolean) {
    abort();
    setOpen(next);
    if (next) {
      setDraft(null);
      setProgress(null);
      setFailure(null);
      resetAi();
      apply.reset();
      props.onOpen();
    }
  }

  function generate() {
    abort();
    const current = new AbortController();
    controller.current = current;
    setFailure(null);
    ai.mutate(
      { body: props.buildBody(), signal: current.signal },
      {
        onSuccess: ({ result, context }) => {
          const picked = select(result);
          setDraft({ items: toDraft(picked.items), warnings: picked.warnings, context });
        },
      },
    );
  }

  function cancel() {
    abort();
    resetAi();
  }

  function accept() {
    if (!draft) return;
    const pending = pendingItems(draft.items);
    const alreadyCreated = draft.items.filter((item) => item.created).length;
    setFailure(null);
    setProgress({ done: 0, total: pending.length });
    apply.mutate(
      {
        items: pending.map((item) => ({ key: item.key, input: { source: item.source, title: item.title } })),
        create: (input, key) => create(input.source, input.title, key),
        onProgress: (done, total) => setProgress({ done, total }),
      },
      {
        onSuccess: (outcome) => {
          setProgress(null);
          if (outcome.failure === null) {
            toast.success(props.successMessage(outcome.createdKeys.length));
            show(false);
            return;
          }
          setDraft({ ...draft, items: markCreated(draft.items, outcome.createdKeys) });
          setFailure(
            `Đã tạo ${alreadyCreated + outcome.createdKeys.length}/${alreadyCreated + pending.length}. Lỗi: ${issueWriteErrorMessage(outcome.failure.error)}`,
          );
        },
      },
    );
  }

  const busy = ai.isPending || apply.isPending;
  const pendingCount = draft ? pendingItems(draft.items).length : 0;
  const retrying = draft?.items.some((item) => item.created) ?? false;
  const acceptLabel = progress
    ? `Đang tạo ${progress.done}/${progress.total}…`
    : retrying
      ? "Thử lại phần còn lại"
      : `Tạo ${pendingCount} ${props.noun}`;

  return (
    <>
      <Button type="button" variant="outline" size={props.triggerSize} onClick={() => show(true)}>
        <Sparkles aria-hidden />
        {props.triggerLabel}
      </Button>
      <Dialog open={open} onOpenChange={show}>
        {/* Panel issue lắng nghe Escape ở document; chặn lan để Escape chỉ đóng hộp này. */}
        <DialogContent
          className="max-h-[90vh] overflow-y-auto sm:max-w-2xl"
          onEscapeKeyDown={(event) => event.stopPropagation()}
        >
          <DialogHeader>
            <DialogTitle>{props.title}</DialogTitle>
            <DialogDescription>{props.description}</DialogDescription>
          </DialogHeader>

          {draft === null ? (
            <div className="space-y-4">
              <fieldset className="min-w-0 space-y-3" disabled={ai.isPending}>
                {props.form}
              </fieldset>
              <AiRunStatus pending={ai.isPending} error={ai.error} onCancel={cancel} />
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => show(false)}>
                  Đóng
                </Button>
                <Button type="button" onClick={generate} disabled={!props.canGenerate || ai.isPending}>
                  Tạo gợi ý
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4">
              <AiContextNotes warnings={draft.warnings} context={draft.context} />
              {props.reviewNote}
              {draft.items.length === 0 ? (
                <p className="text-sm text-muted-foreground">{props.emptyMessage}</p>
              ) : (
                <AiProposalList
                  items={draft.items}
                  disabled={apply.isPending}
                  onTitle={(index, value) => setDraft({ ...draft, items: setTitle(draft.items, index, value) })}
                  onSelected={(index, value) => setDraft({ ...draft, items: setSelected(draft.items, index, value) })}
                  renderDetails={props.renderDetails}
                />
              )}
              {failure ? (
                <p className="text-sm text-destructive" role="alert">
                  {failure}
                </p>
              ) : null}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => show(false)} disabled={apply.isPending}>
                  Hủy
                </Button>
                <Button type="button" variant="outline" onClick={() => setDraft(null)} disabled={busy || retrying}>
                  Tạo lại
                </Button>
                <Button type="button" onClick={accept} disabled={pendingCount === 0 || busy}>
                  {acceptLabel}
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
