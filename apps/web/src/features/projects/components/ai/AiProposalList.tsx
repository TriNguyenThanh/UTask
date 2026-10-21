import type { ReactNode } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import type { DraftItem } from "@/features/projects/lib/aiDraft";

/** Danh sách gợi ý: chọn/bỏ và sửa tiêu đề. Dòng đã tạo bị khóa. */
export function AiProposalList<S>({
  items,
  onTitle,
  onSelected,
  disabled,
  renderDetails,
}: Readonly<{
  items: readonly DraftItem<S>[];
  onTitle: (index: number, title: string) => void;
  onSelected: (index: number, selected: boolean) => void;
  disabled: boolean;
  renderDetails: (source: S) => ReactNode;
}>) {
  return (
    <ul className="space-y-3">
      {items.map((item, index) => (
        <li key={item.id} className="space-y-2 rounded-md border p-3">
          <div className="flex items-center gap-2">
            <Checkbox
              aria-label={`Chọn đề xuất ${index + 1}`}
              checked={item.selected}
              disabled={disabled || item.created}
              onCheckedChange={(checked) => onSelected(index, checked === true)}
            />
            <Input
              aria-label={`Tiêu đề đề xuất ${index + 1}`}
              value={item.title}
              maxLength={300}
              disabled={disabled || item.created}
              onChange={(event) => onTitle(index, event.target.value)}
            />
            {item.created ? (
              <span className="shrink-0 rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                Đã tạo
              </span>
            ) : null}
          </div>
          <div className="space-y-1 pl-6 text-xs text-muted-foreground">{renderDetails(item.source)}</div>
        </li>
      ))}
    </ul>
  );
}
