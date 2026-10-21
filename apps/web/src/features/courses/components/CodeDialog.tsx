import type { UseMutationResult } from "@tanstack/react-query";
import { useId, useState } from "react";
import { toast } from "sonner";
import { KeyRound } from "lucide-react";

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
import { newIdempotencyKey } from "@/lib/api/idempotency";

export interface CodeDialogCopy {
  trigger: string;
  title: string;
  description: string;
  label: string;
  success: string;
}

type JoinMutation = UseMutationResult<unknown, Error, { code: string; idempotencyKey: string }>;

/** Hộp thoại nhập mã (lớp hoặc nhóm). Khóa Idempotency sinh một lần mỗi lần mở. */
export function CodeDialog({ copy, mutation: joinClass }: Readonly<{ copy: CodeDialogCopy; mutation: JoinMutation }>) {
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      // Mỗi lần mở là một ý định mới; gửi lại trong cùng lần mở dùng cùng khóa.
      setIdempotencyKey(newIdempotencyKey());
      setCode("");
      joinClass.reset();
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    joinClass.mutate(
      { code, idempotencyKey },
      {
        onSuccess: () => {
          toast.success(copy.success);
          setOpen(false);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <KeyRound className="size-4" aria-hidden />
          {copy.trigger}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{copy.title}</DialogTitle>
            <DialogDescription>{copy.description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor={inputId}>{copy.label}</Label>
            <Input
              id={inputId}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              autoComplete="off"
              aria-invalid={joinClass.isError ? true : undefined}
            />
            {joinClass.isError ? (
              <p className="text-sm text-destructive" role="alert">
                {joinClass.error.message}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" disabled={code.trim() === "" || joinClass.isPending}>
              Tham gia
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
