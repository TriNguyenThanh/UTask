import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Màn trạng thái một bước (thành công, liên kết không hợp lệ) cho các trang xác thực. */
export function AuthStatusCard({
  icon: Icon,
  title,
  children,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="w-full max-w-[400px]" aria-labelledby="auth-status-title">
      <div className="mb-3 grid size-11 place-items-center rounded-lg bg-primary-subtle text-primary">
        <Icon className="size-6" aria-hidden="true" />
      </div>
      <h1 id="auth-status-title" className="mb-2 text-2xl font-semibold tracking-tight">
        {title}
      </h1>
      <div className="mb-6 text-sm leading-relaxed text-muted-foreground" role="status">
        {children}
      </div>
      {actions ? <div className="flex flex-wrap gap-3 text-sm font-medium">{actions}</div> : null}
    </section>
  );
}
