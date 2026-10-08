import { useId } from "react";

import { cn } from "@/lib/utils";

/**
 * Native select with a visible label: keyboard- and screen-reader-friendly,
 * and the system picker on mobile. Used for filters stored in the URL.
 */
export function FilterSelect({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
