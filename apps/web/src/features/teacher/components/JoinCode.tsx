import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/**
 * Copies the join code and reports the truth: success only when the clipboard
 * write really succeeded, otherwise tells the person to copy it by hand.
 */
export async function copyJoinCode(code: string) {
  try {
    if (!navigator.clipboard?.writeText) {
      throw new Error("Clipboard không khả dụng");
    }
    await navigator.clipboard.writeText(code);
    toast.success("Đã sao chép mã tham gia.");
  } catch {
    toast.error("Không sao chép được mã. Hãy chọn mã và sao chép thủ công.");
  }
}

export function CopyJoinCodeButton({ code }: Readonly<{ code: string }>) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="size-7"
      aria-label="Sao chép mã tham gia"
      onClick={() => void copyJoinCode(code)}
    >
      <Copy className="size-3.5" aria-hidden />
    </Button>
  );
}
