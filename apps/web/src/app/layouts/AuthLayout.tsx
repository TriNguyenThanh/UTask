import { LifeBuoy } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export function AuthLayout({
  children,
  headerActions,
}: {
  children: ReactNode;
  headerActions?: ReactNode;
}) {
  return (
    <div className="flex min-h-svh flex-col bg-[#faf9f8] text-[#1a1c1c]">
      <header className="w-full border-b border-[#e5e3df] bg-[#faf9f8]">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-4 sm:px-6">
          <Link className="flex items-center gap-2.5" to="/login" aria-label="UTask — về trang đăng nhập">
            <span className="grid size-7 place-items-center rounded-md bg-primary text-xs font-bold tracking-tight text-primary-foreground">
              UT
            </span>
            <span className="text-sm font-semibold tracking-tight">UTask</span>
            <span className="rounded bg-primary-subtle px-2 py-0.5 text-xs font-medium tracking-wide text-primary">
              Academic SSO
            </span>
          </Link>
          {headerActions ? (
            <div className="flex items-center gap-3 text-xs text-[#787586]">{headerActions}</div>
          ) : null}
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-10 md:py-12">
        {children}
      </main>

      <footer className="w-full border-t border-[#e5e3df] bg-[#faf9f8] py-4">
        <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-3 px-4 text-center text-xs text-[#787586] sm:px-6 lg:flex-row lg:text-left">
          <p>© 2026 UTask Academic Platform · Đại học Quốc gia TP.HCM</p>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2" aria-label="Thông tin nền tảng">
            <span>Quy chế đồ án</span>
            <span>Chính sách bảo mật SSO</span>
            <span className="inline-flex items-center gap-1">
              <LifeBuoy className="size-3.5" aria-hidden="true" />
              Hướng dẫn sử dụng
            </span>
            <span>Trạng thái hệ thống</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
