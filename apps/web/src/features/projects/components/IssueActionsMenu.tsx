import { MoreHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface IssueMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
}

export interface IssueMenuGroup {
  label?: string;
  items: IssueMenuItem[];
}

/**
 * The non-drag way to do everything a drag does (WCAG 2.5.7): one button per
 * card that opens a menu of outcomes. The button is named after the card so a
 * screen reader user hears which card the menu belongs to.
 */
export function IssueActionsMenu({
  issueKey,
  groups,
}: Readonly<{
  issueKey: string;
  groups: IssueMenuGroup[];
}>) {
  const visible = groups.filter((group) => group.items.length > 0);
  if (visible.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="size-6"
          data-issue-trigger={issueKey}
          data-drag-ignore
          aria-label={`Thao tác cho ${issueKey}`}
        >
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {visible.map((group, index) => (
          <div key={group.label ?? index}>
            {index > 0 ? <DropdownMenuSeparator /> : null}
            {group.label ? <DropdownMenuLabel>{group.label}</DropdownMenuLabel> : null}
            {group.items.map((item) => (
              <DropdownMenuItem key={item.id} onSelect={item.onSelect}>
                {item.label}
              </DropdownMenuItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
