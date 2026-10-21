import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { DiscardChangesConfirm } from "@/components/feedback/DiscardChangesConfirm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ClassCreateForm } from "@/features/teacher/components/ClassCreateForm";
import { DemoClassCreateForm } from "@/features/teacher/components/DemoClassCreateForm";
import { isRealService } from "@/lib/config/services";

/**
 * Nút "Tạo lớp" mở hộp thoại ngay tại trang hiện tại (không chuyển trang). Esc hoặc nhấp ra ngoài khi form đã
 * nhập dở thì hỏi lại trước khi bỏ; "Hủy" và nút × đóng ngay. Tạo xong thì vào trang lớp mới.
 */
export function CreateClassButton() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  function close() {
    setOpen(false);
    setDirty(false);
  }

  // Esc và nhấp ra ngoài dễ bấm nhầm nên hỏi lại khi form đã nhập dở; "Hủy" và nút × đóng ngay.
  function askBeforeDiscard(event: Event) {
    if (!dirty) return;
    event.preventDefault();
    setConfirmDiscard(true);
  }

  return (
    <>
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button>Tạo lớp</Button>
      </DialogTrigger>
      <DialogContent
        className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl"
        onInteractOutside={askBeforeDiscard}
        onEscapeKeyDown={askBeforeDiscard}
      >
        <DialogHeader className="space-y-1 border-b px-6 py-5 pr-12 text-left">
          <DialogTitle>Tạo lớp</DialogTitle>
          <DialogDescription>
            Chọn môn học, rồi nhập thông tin lớp bạn sẽ phụ trách.
          </DialogDescription>
        </DialogHeader>
        {isRealService("classroom") ? (
          <ClassCreateForm
            onCancel={close}
            onDirtyChange={setDirty}
            onCreated={(classId) => {
              close();
              toast.success("Đã tạo lớp.");
              void navigate(`/teacher/courses/${classId}`);
            }}
          />
        ) : (
          <DemoClassCreateForm onCancel={close} onDirtyChange={setDirty} />
        )}
      </DialogContent>
    </Dialog>
    <DiscardChangesConfirm
      open={confirmDiscard}
      onDiscard={() => {
        setConfirmDiscard(false);
        close();
      }}
      onKeepEditing={() => setConfirmDiscard(false)}
    />
    </>
  );
}
