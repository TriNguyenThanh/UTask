import { useEffect } from "react";
import { useBlocker } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Rời trang khi form còn chỉnh sửa chưa lưu thì hỏi trước, dù rời bằng cách nào:
 * điều hướng trong ứng dụng do blocker xử lý, đóng tab hay tải lại do `beforeunload`.
 */
export function UnsavedChangesGuard({ dirty }: Readonly<{ dirty: boolean }>) {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  return (
    <Dialog open={blocker.state === "blocked"} onOpenChange={(open) => !open && blocker.reset?.()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rời khỏi trang?</DialogTitle>
          <DialogDescription>
            Thông tin bạn đã nhập chưa được lưu ở đâu cả và sẽ mất nếu rời trang.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => blocker.reset?.()}>
            Ở lại và tiếp tục nhập
          </Button>
          <Button variant="destructive" onClick={() => blocker.proceed?.()}>
            Rời trang
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
