import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { validateLabelForm } from "@/features/projects/lib/labelForm";
import { issueWriteErrorMessage } from "@/features/projects/lib/moveErrors";
import type { LabelDto } from "@/lib/api/work/dto";
import { useCreateLabel, useDeleteLabel, useLabelsReal, usePatchLabel } from "@/lib/query/workMetaHooks";

const DEFAULT_COLOR = "#2563eb";

/** Quản lý nhãn của dự án (Leader): thêm, đổi tên/màu, xóa. Xóa nhãn gỡ nó khỏi mọi issue. */
export function LabelManagerDialog({
  projectId,
  open,
  onOpenChange,
}: Readonly<{ projectId: string; open: boolean; onOpenChange: (open: boolean) => void }>) {
  const labels = useLabelsReal(projectId, open);
  const create = useCreateLabel(projectId);
  const patch = usePatchLabel(projectId);
  const remove = useDeleteLabel(projectId);
  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [formError, setFormError] = useState<string | null>(null);
  const [editing, setEditing] = useState<LabelDto | null>(null);
  const [toDelete, setToDelete] = useState<LabelDto | null>(null);

  const busy = create.isPending || patch.isPending;
  const error = create.error ?? patch.error ?? remove.error;

  function cancelEdit() {
    setEditing(null);
    setName("");
    setColor(DEFAULT_COLOR);
    setFormError(null);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateLabelForm({ name, color });
    setFormError(invalid);
    if (invalid) return;
    const input = { name: name.trim(), color };
    if (editing) {
      patch.mutate({ labelId: editing.id, ...input }, { onSuccess: cancelEdit });
    } else {
      create.mutate(input, { onSuccess: cancelEdit });
    }
  }

  function confirmRemove() {
    if (!toDelete) return;
    remove.mutate(toDelete.id, {
      onSuccess: () => toast.success("Đã xóa nhãn."),
      onSettled: () => setToDelete(null),
    });
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Quản lý nhãn</DialogTitle>
            <DialogDescription>Nhãn dùng để phân loại issue trong dự án.</DialogDescription>
          </DialogHeader>
          {formError || error ? (
            <p className="text-sm text-destructive" role="alert">
              {formError ?? issueWriteErrorMessage(error)}
            </p>
          ) : null}
          <ul className="space-y-1.5" aria-label="Danh sách nhãn">
            {labels.isPending ? <li className="text-xs text-muted-foreground">Đang tải...</li> : null}
            {labels.data?.length === 0 ? <li className="text-xs text-muted-foreground">Chưa có nhãn nào.</li> : null}
            {labels.data?.map((label) => (
              <li key={label.id} className="flex items-center gap-2 text-sm">
                <span className="size-3 shrink-0 rounded-full" style={{ backgroundColor: label.color }} aria-hidden />
                <span className="min-w-0 flex-1 truncate">{label.name}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    setEditing(label);
                    setName(label.name);
                    setColor(label.color);
                    setFormError(null);
                  }}
                  aria-label={`Sửa nhãn ${label.name}`}
                >
                  Sửa
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="text-destructive"
                  onClick={() => setToDelete(label)}
                  aria-label={`Xóa nhãn ${label.name}`}
                >
                  Xóa
                </Button>
              </li>
            ))}
          </ul>
          <form className="flex items-end gap-2" onSubmit={submit} aria-label={editing ? "Sửa nhãn" : "Thêm nhãn"}>
            <fieldset className="flex min-w-0 flex-1 items-end gap-2" disabled={busy}>
              <Input
                value={name}
                maxLength={50}
                placeholder="Tên nhãn"
                aria-label="Tên nhãn"
                onChange={(event) => {
                  setName(event.target.value);
                  setFormError(null);
                }}
              />
              <input
                type="color"
                value={color}
                aria-label="Màu nhãn"
                className="h-9 w-10 shrink-0 cursor-pointer rounded-md border border-input bg-background p-1"
                onChange={(event) => setColor(event.target.value)}
              />
            </fieldset>
            <Button type="submit" size="sm" disabled={!name.trim() || busy}>
              {editing ? "Lưu" : "Thêm"}
            </Button>
            {editing ? (
              <Button type="button" variant="outline" size="sm" onClick={cancelEdit}>
                Hủy
              </Button>
            ) : null}
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={toDelete !== null}
        title={`Xóa nhãn "${toDelete?.name ?? ""}"?`}
        description="Nhãn sẽ được gỡ khỏi mọi issue đang dùng nó."
        confirmLabel="Xóa nhãn"
        destructive
        pending={remove.isPending}
        onConfirm={confirmRemove}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
