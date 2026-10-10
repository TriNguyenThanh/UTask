import { CheckSquare2, LogOut, Menu } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { AppSidebar } from "@/components/navigation/AppSidebar";
import { TeacherSidebar } from "@/components/navigation/TeacherSidebar";
import { TeacherTopNavigation } from "@/components/navigation/TeacherTopNavigation";
import { TopNavigation } from "@/components/navigation/TopNavigation";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useAuth } from "@/features/auth/AuthProvider";
import { canUseTeacherSpace, isStudentAccount } from "@/features/auth/utils";
import { TeacherChromeContext } from "@/app/layouts/TeacherChromeContext";

function UserSummary({ onLogout }: Readonly<{ onLogout: () => void }>) {
  const { user } = useAuth();
  return (
    <details className="group relative">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 rounded-lg px-2 hover:bg-muted">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary-subtle text-xs font-bold text-primary">
          {user?.display_name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 text-left">
          <span className="block truncate text-sm font-medium">{user?.display_name}</span>
          <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
        </span>
      </summary>
      <div className="absolute bottom-full left-0 z-20 mb-2 w-full rounded-lg border bg-popover p-1 shadow-lg">
        <Button className="w-full justify-start" variant="ghost" onClick={onLogout}>
          <LogOut aria-hidden="true" /> Đăng xuất
        </Button>
      </div>
    </details>
  );
}

function SidebarShell({ children, home }: Readonly<{ children: ReactNode; home: string }>) {
  return (
    <>
      <div className="flex h-16 items-center border-b border-sidebar-border px-5">
        <NavLink className="flex items-center gap-2.5" to={home} aria-label="UTask — Trang chủ">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            UT
          </span>
          <span className="flex flex-col">
            <span className="text-[15px] font-bold leading-none tracking-tight">UTask</span>
            <span className="mt-1 text-[11px] font-medium text-muted-foreground">
              Academic Portal
            </span>
          </span>
        </NavLink>
      </div>
      {children}
    </>
  );
}

export function AuthenticatedLayout() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
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
  const sidebar = inTeacherSpace ? <TeacherSidebar /> : <AppSidebar />;

  // Any navigation (including search-param deep links from task rows or
  // notifications) must close the mobile drawer so the page is visible.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname, location.search]);
  function logout() {
    void auth.logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[var(--sidebar-width)_minmax(0,1fr)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Bỏ qua điều hướng
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden min-h-screen flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <SidebarShell home={inTeacherSpace ? "/teacher" : "/my-work"}>
          {sidebar}
        </SidebarShell>
        <div className="border-t border-sidebar-border bg-secondary/70 p-3">
          <UserSummary onLogout={logout} />
        </div>
      </aside>

      <div className="min-w-0">
        {inTeacherSpace ? (
          <TeacherTopNavigation onOpenMobileNav={() => setMobileOpen(true)} />
        ) : (
          <TopNavigation onOpenMobileNav={() => setMobileOpen(true)} />
        )}
        <main className="min-w-0 pb-16" id="main-content">
          <TeacherChromeContext.Provider value={setInstructorProjectView}>
            <Outlet />
          </TeacherChromeContext.Provider>
        </main>
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
          <div className="flex min-h-0 flex-1 flex-col">{sidebar}</div>
          <div className="border-t border-sidebar-border p-3">
            <UserSummary onLogout={logout} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}