import { cn } from "@/lib/utils";

/** Segmented pill tabs (cùng phong cách bộ lọc Thông báo, cỡ lớn hơn cho điều hướng mục). */
export const segmentedTabsListClass =
  "inline-flex max-w-full items-center gap-1 self-start overflow-x-auto rounded-lg bg-secondary p-1 text-sm font-medium";

export function segmentedTabClass(active: boolean) {
  return cn(
    "flex items-center gap-2 whitespace-nowrap rounded-md px-4 py-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
    active
      ? "bg-card font-semibold text-foreground shadow-sm"
      : "text-muted-foreground hover:text-foreground",
  );
}
