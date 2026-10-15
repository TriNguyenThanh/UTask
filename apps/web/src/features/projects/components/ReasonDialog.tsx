import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const schema = z.object({
  reason: z.string().trim().min(3, "Vui lòng nêu lý do (ít nhất 3 ký tự).").max(500, "Tối đa 500 ký tự."),
});

type ReasonValues = z.infer<typeof schema>;

/**
 * Asks for a written reason before a change that must leave one behind:
 * blocking a task, or changing the scope of a running sprint. Closing the
 * dialog without submitting changes nothing.
 */
export function ReasonDialog({
  open,
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
}: Readonly<{
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}>) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReasonValues>({ resolver: zodResolver(schema), defaultValues: { reason: "" } });

  // A fresh dialog each time: never show the previous reason.
  useEffect(() => {
    if (open) reset({ reason: "" });
  }, [open, reset]);

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent>
        <form onSubmit={handleSubmit((values) => onConfirm(values.reason))} noValidate>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-4">
            <Label htmlFor="issue-reason">Lý do</Label>
            <Textarea
              id="issue-reason"
              rows={3}
              aria-invalid={errors.reason ? true : undefined}
              aria-describedby={errors.reason ? "issue-reason-error" : undefined}
              {...register("reason")}
            />
            {errors.reason ? (
              <p id="issue-reason-error" role="alert" className="text-xs text-destructive">
                {errors.reason.message}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              Hủy
            </Button>
            <Button type="submit">{confirmLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
