import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";

/**
 * Hỏi lại khi đóng bằng thao tác dễ bấm nhầm (Esc, nhấp ra ngoài) lúc còn nội dung chưa lưu.
 * Nút đóng rõ ràng (×, "Hủy", "Đóng") đóng ngay, không cần hộp này.
 */
export function DiscardChangesConfirm({
  open,
  onDiscard,
  onKeepEditing,
}: Readonly<{ open: boolean; onDiscard: () => void; onKeepEditing: () => void }>) {
  return (
    <ConfirmDialog
      open={open}
      title="Bỏ thông tin đã nhập?"
      description="Nội dung bạn vừa nhập chưa được lưu và sẽ mất nếu đóng."
      confirmLabel="Bỏ thay đổi"
      destructive
      onConfirm={onDiscard}
      onCancel={onKeepEditing}
    />
  );
}
