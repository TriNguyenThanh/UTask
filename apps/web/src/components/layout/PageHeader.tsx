import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? <p className="text-sm font-semibold text-primary">{eyebrow}</p> : null}
        <h1 className="mt-1 truncate text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children ? <div className="flex shrink-0 flex-wrap gap-2">{children}</div> : null}
    </header>
  );
}
