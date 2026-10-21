import { useId, type ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

type DisabledActionProps = Omit<
  ComponentProps<typeof Button>,
  "disabled" | "onClick" | "type" | "title" | "asChild"
> & { reason: string };

/**
 * Nút cho chức năng chưa khả dụng. Không dùng `disabled` thật để vẫn focus/chạm được:
 * bấm, chạm, Enter hoặc Space mở popover nêu lý do; lý do cũng là mô tả cho trình đọc màn hình.
 */
export function DisabledAction({
  reason,
  className,
  variant = "outline",
  children,
  ...buttonProps
}: Readonly<DisabledActionProps>) {
  const reasonId = useId();
  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            {...buttonProps}
            type="button"
            variant={variant}
            aria-disabled="true"
            aria-describedby={reasonId}
            className={cn("cursor-not-allowed opacity-50", className)}
          >
            {children}
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" className="w-72 text-sm">
          {reason}
        </PopoverContent>
      </Popover>
      <span id={reasonId} className="sr-only">
        {reason}
      </span>
    </>
  );
}
