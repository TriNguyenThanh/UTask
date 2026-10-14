import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title?: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-dashed bg-card px-6 py-12 text-center">
      {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
      <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </section>
  );
}
