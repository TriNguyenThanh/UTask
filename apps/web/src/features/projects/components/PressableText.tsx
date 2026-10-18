import type { KeyboardEvent, ReactNode } from "react";

/**
 * A control that acts like a button but is not a <button> element. A card is
 * dragged by pressing anywhere on it, and Firefox will not start a drag from
 * a real <button>; a role="button" element keeps the keyboard and screen
 * reader behaviour without that limit.
 */
export function PressableText({
  onActivate,
  label,
  className,
  children,
}: Readonly<{
  onActivate: () => void;
  /** Accessible name. */
  label: string;
  className?: string;
  children: ReactNode;
}>) {
  function onKeyDown(event: KeyboardEvent<HTMLSpanElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate();
    }
  }
  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onActivate}
      onKeyDown={onKeyDown}
      className={className}
    >
      {children}
    </span>
  );
}
