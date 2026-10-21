import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Vùng nhập của hộp thoại tạo lớp: cuộn riêng để tiêu đề và hàng nút luôn nằm yên. */
export function FormBody({ children }: Readonly<{ children: ReactNode }>) {
  return <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-6 py-5">{children}</div>;
}

/**
 * Một phần của form. Có `title` thì mở đầu bằng biểu tượng và tiêu đề; không có thì chỉ là nhóm ô nhập. Không
 * đánh số bước, không câu giải thích.
 */
export function FormSection({
  icon: Icon,
  title,
  children,
}: Readonly<{ icon?: LucideIcon; title?: string; children: ReactNode }>) {
  return (
    <section className="space-y-4">
      {title ? (
        <div className="flex items-center gap-3">
          {Icon ? (
            <span
              aria-hidden
              className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            >
              <Icon className="size-4" />
            </span>
          ) : null}
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Hàng nút cố định ở đáy hộp thoại, nằm ngoài vùng cuộn. */
export function FormFooter({ children }: Readonly<{ children: ReactNode }>) {
  return <div className="flex flex-wrap justify-end gap-2 border-t bg-muted/40 px-6 py-4">{children}</div>;
}
