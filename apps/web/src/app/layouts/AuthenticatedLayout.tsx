import { Bell, LogOut, Menu, Pin, PinOff, Settings } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useMatches,
  useNavigate,
  type UIMatch,
} from "react-router-dom";

import { AppSidebar } from "@/components/navigation/AppSidebar";
import { TeacherSidebar } from "@/components/navigation/TeacherSidebar";
import { TopBar } from "@/components/navigation/TopBar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useAuth } from "@/features/auth/AuthProvider";
import { useSignOut } from "@/features/auth/useSignOut";
import { canUseTeacherSpace, isStudentAccount } from "@/features/auth/utils";
import { TeacherChromeContext } from "@/app/layouts/TeacherChromeContext";
import { PageTitleContext } from "@/app/layouts/PageTitleContext";
import { cn } from "@/lib/utils";

const SIDEBAR_PINNED_KEY = "utask.sidebar.pinned";

/** Mặc định ghim (mở rộng cố định); chỉ "0" mới là bỏ ghim. */
function readSidebarPinned(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_PINNED_KEY) !== "0";
  } catch {
    return true;
  }
}

function writeSidebarPinned(pinned: boolean) {
  try {
    localStorage.setItem(SIDEBAR_PINNED_KEY, pinned ? "1" : "0");
  } catch {
    // Storage bị chặn: trạng thái chỉ giữ trong phiên.
  }
}

function titleFromMatches(matches: readonly UIMatch[]): string {
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const handle = matches[index].handle as { title?: string } | undefined;
    if (handle?.title) return handle.title;
  }
  return "UTask";
}

function UserSummary({
  onLogout,
  collapsed,
  onOpenChange,
}: Readonly<{
  onLogout: () => void;
  collapsed: boolean;
  onOpenChange?: (open: boolean) => void;
}>) {
  const { user } = useAuth();
  return (
    <DropdownMenu onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={collapsed ? (user?.display_name ?? "Tài khoản") : undefined}
          className="flex min-h-11 short:min-h-9 w-full items-center gap-3 rounded-lg px-1 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-subtle text-xs font-bold text-primary">
            {user?.display_name.slice(0, 1).toUpperCase()}
          </span>
          <span
            className={cn(
              "min-w-0 flex-1 transition-opacity duration-200",
              collapsed && "opacity-0",
            )}
          >
            <span className="block truncate text-sm font-medium">{user?.display_name}</span>
            <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate text-sm font-medium">{user?.display_name}</span>
          <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/settings/profile">
            <Settings aria-hidden="true" /> Cài đặt tài khoản
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/notifications">
            <Bell aria-hidden="true" /> Thông báo
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout}>
          <LogOut aria-hidden="true" /> Đăng xuất
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SidebarShell({
  children,
  home,
  collapsed,
  pin,
}: Readonly<{
  children: ReactNode;
  home: string;
  collapsed: boolean;
  /** Chỉ có ở sidebar desktop; drawer mobile không có nút ghim. */
  pin?: { pinned: boolean; onToggle: () => void };
}>) {
  return (
    <>
      <div className="flex h-16 short:h-12 shrink-0 items-center gap-2 border-b border-sidebar-border px-4">
        <NavLink className="flex items-center gap-2.5" to={home} aria-label="UTask — Trang chủ">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            UT
          </span>
          <span
            className={cn(
              "flex flex-col whitespace-nowrap transition-opacity duration-200",
              collapsed && "opacity-0",
            )}
          >
            <span className="text-[15px] font-bold leading-none tracking-tight">UTask</span>
            <span className="mt-1 text-[11px] font-medium text-muted-foreground">
              Academic Portal
            </span>
          </span>
        </NavLink>
        {pin ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn(
              "ml-auto size-8 shrink-0 transition-opacity duration-200",
              collapsed && "pointer-events-none opacity-0",
            )}
            tabIndex={collapsed ? -1 : 0}
            aria-pressed={pin.pinned}
            aria-label={pin.pinned ? "Bỏ ghim thanh điều hướng" : "Ghim thanh điều hướng"}
            title={pin.pinned ? "Bỏ ghim" : "Ghim"}
            onClick={pin.onToggle}
          >
            {pin.pinned ? (
              <Pin className="size-4 fill-current" aria-hidden />
            ) : (
              <PinOff className="size-4" aria-hidden />
            )}
          </Button>
        ) : null}
      </div>
      {children}
    </>
  );
}

export function AuthenticatedLayout() {
  const auth = useAuth();
  const navigate = useNavigate();
  const signOut = useSignOut();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [pinned, setPinned] = useState(readSidebarPinned);
  const [hovered, setHovered] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const mainRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const [instructorProjectView, setInstructorProjectView] = useState(false);
  // The Teacher chrome (sidebar, top bar) is used only inside /teacher by an
  // account that may use it, so a blocked account never triggers Teacher
  // queries and Student pages never show Teacher navigation.
  const inTeacherArea = location.pathname === "/teacher" || location.pathname.startsWith("/teacher/");
  // A project opened by its class's instructor shows Teacher navigation. A
  // teacher-only account gets it at once (it has no Student navigation to
  // load); an account that is also a student gets it once the workspace says
  // the viewer is an instructor.
  const inInstructorProject =
    location.pathname.startsWith("/projects/") &&
    canUseTeacherSpace(auth.user) &&
    (!isStudentAccount(auth.user) || instructorProjectView);
  const inTeacherSpace = (inTeacherArea && canUseTeacherSpace(auth.user)) || inInstructorProject;
  // Unpinned: a rail that opens over the page while hovered / focused / its
  // account menu is open, and shrinks back afterwards. Pinned: always open.
  const collapsed = !pinned && !hovered && !menuOpen;
  const sidebar = inTeacherSpace ? (
    <TeacherSidebar collapsed={collapsed} />
  ) : (
    <AppSidebar collapsed={collapsed} />
  );
  // The mobile drawer is always expanded.
  const mobileSidebar = inTeacherSpace ? <TeacherSidebar /> : <AppSidebar />;
  const [pageTitle, setPageTitle] = useState<string | null>(null);
  const matches = useMatches();
  const title = pageTitle ?? titleFromMatches(matches);

  // Any navigation (including search-param deep links from task rows or
  // notifications) must close the mobile drawer so the page is visible.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname, location.search]);
  // The page scrolls inside <main> on desktop, so a new route starts at the top.
  useEffect(() => {
    // jsdom has no Element.scrollTo.
    mainRef.current?.scrollTo?.({ top: 0 });
  }, [location.pathname]);
  function logout() {
    void signOut();
  }
  function togglePinned() {
    setPinned((value) => {
      writeSidebarPinned(!value);
      return !value;
    });
  }

  return (
    <div
      className={cn(
        "relative min-h-screen bg-background lg:grid lg:h-svh lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden lg:transition-[grid-template-columns] lg:duration-200 lg:ease-in-out",
        pinned
          ? "lg:grid-cols-[var(--sidebar-width)_minmax(0,1fr)]"
          : "lg:grid-cols-[var(--sidebar-rail-width)_minmax(0,1fr)]",
      )}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Bỏ qua điều hướng
      </a>

      {/* Desktop sidebar: the grid cell reserves the pinned/rail width, the
          aside inside it animates its own width and floats over the page. */}
      <div className="relative hidden lg:block lg:min-h-0">
        <aside
          className={cn(
            "absolute inset-y-0 left-0 z-30 flex flex-col overflow-hidden border-r border-sidebar-border bg-sidebar transition-[width,box-shadow] duration-200 ease-in-out",
            collapsed ? "w-[var(--sidebar-rail-width)]" : "w-[var(--sidebar-width)]",
            !pinned && !collapsed && "shadow-xl",
          )}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onFocus={() => setHovered(true)}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setHovered(false);
          }}
        >
          <SidebarShell
            home={inTeacherSpace ? "/teacher" : "/my-work"}
            collapsed={collapsed}
            pin={{ pinned, onToggle: togglePinned }}
          >
            {sidebar}
          </SidebarShell>
          <div className="shrink-0 border-t border-sidebar-border bg-secondary/70 p-3 short:p-2">
            <UserSummary onLogout={logout} collapsed={collapsed} onOpenChange={setMenuOpen} />
          </div>
        </aside>
      </div>

      <div className="flex min-h-svh min-w-0 flex-col lg:min-h-0">
        <TopBar
          title={title}
          inTeacherSpace={inTeacherSpace}
          onOpenMobileNav={() => setMobileOpen(true)}
        />
        {/* The scroll area holds both page and footer, so the footer sits at the
            end of the content (or the viewport bottom when the page is short). */}
        <div ref={mainRef} className="flex min-w-0 flex-1 flex-col lg:min-h-0 lg:overflow-y-auto">
          <main className="min-w-0 flex-1 pb-8 short:pb-4" id="main-content">
            <TeacherChromeContext.Provider value={setInstructorProjectView}>
              <PageTitleContext.Provider value={setPageTitle}>
                <Outlet />
              </PageTitleContext.Provider>
            </TeacherChromeContext.Provider>
          </main>
          <footer className="shrink-0 border-t bg-background px-4 py-2.5 text-center text-[11px] text-muted-foreground lg:px-8">
            UTask Academic Portal • Quản lý đồ án &amp; Nghiên cứu khoa học sinh viên
          </footer>
        </div>
      </div>

      {/* Mobile drawer */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="flex w-[min(20rem,88vw)] flex-col p-0">
          <SheetHeader className="border-b border-sidebar-border px-5 py-3">
            <SheetTitle className="text-left text-[15px] font-bold tracking-tight">
              UTask
            </SheetTitle>
            <SheetDescription className="text-left text-[11px]">
              Academic Portal
            </SheetDescription>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col">{mobileSidebar}</div>
          <div className="border-t border-sidebar-border p-3">
            <UserSummary onLogout={logout} collapsed={false} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
