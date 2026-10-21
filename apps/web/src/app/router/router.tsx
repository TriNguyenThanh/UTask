import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { RequireAuth } from "@/app/router/RequireAuth";
import { HomeRedirect, RequireTeacherSpace } from "@/app/router/RequireTeacherSpace";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { ProjectIndexRedirect } from "@/features/projects/routes/ProjectIndexRedirect";
import { RouteError } from "@/app/router/RouteError";

/** Exported so tests exercise the real route table, guards included. */
export const appRoutes: RouteObject[] = [
  {
    path: "/login",
    lazy: () => import("@/features/auth/routes/LoginRoute"),
    errorElement: <RouteError />,
  },
  {
    path: "/forgot-password",
    lazy: () => import("@/features/auth/routes/ForgotPasswordRoute"),
    errorElement: <RouteError />,
  },
  {
    path: "/auth/reset",
    lazy: () => import("@/features/auth/routes/ResetPasswordRoute"),
    errorElement: <RouteError />,
  },
  {
    path: "/auth/activate",
    lazy: () => import("@/features/auth/routes/ActivateAccountRoute"),
    errorElement: <RouteError />,
  },
  {
    path: "/register",
    lazy: () => import("@/features/auth/routes/RegisterRoute"),
    errorElement: <RouteError />,
  },
  {
    element: (
      <RequireAuth>
        <AuthenticatedLayout />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
    children: [{ errorElement: <RouteError inShell />, children: [
      { path: "/", element: <HomeRedirect /> },
      {
        path: "/my-work",
        handle: { title: "Trang chủ" },
        lazy: () => import("@/features/my-work/routes/MyWorkRoute"),
      },
      {
        path: "/courses",
        handle: { title: "Môn học" },
        lazy: () => import("@/features/courses/routes/CoursesRoute"),
      },
      {
        path: "/courses/:courseId/team",
        handle: { title: "Môn học" },
        lazy: () => import("@/features/courses/routes/CourseTeamRoute"),
      },
      {
        path: "/projects",
        handle: { title: "Dự án môn học" },
        lazy: () => import("@/features/projects/routes/ProjectsRoute"),
      },
      {
        path: "/projects/:projectId",
        handle: { title: "Dự án" },
        lazy: () => import("@/features/projects/routes/ProjectWorkspaceLayout"),
        children: [
          { index: true, element: <ProjectIndexRedirect /> },
          {
            path: "backlog",
            lazy: () => import("@/features/projects/routes/ProjectBacklogRoute"),
          },
          {
            path: "board",
            lazy: () => import("@/features/projects/routes/ProjectBoardRoute"),
          },
          {
            path: "code",
            lazy: () => import("@/features/projects/routes/ProjectCodeRoute"),
          },
          {
            path: "settings",
            element: <RequireProjectManagePermission />,
            children: [
              {
                path: "",
                lazy: () => import("@/features/projects/routes/ProjectSettingsRoute"),
              },
            ],
          },
          { path: "info", lazy: () => import("@/features/projects/routes/ProjectInfoRoute") },
        ],
      },
      {
        path: "/teacher",
        handle: { title: "Không gian giảng viên" },
        element: <RequireTeacherSpace />,
        children: [
          {
            index: true,
            handle: { title: "Bàn làm việc giảng viên" },
            lazy: () => import("@/features/teacher/routes/TeacherHomeRoute"),
          },
          {
            path: "courses",
            handle: { title: "Lớp phụ trách" },
            lazy: () => import("@/features/teacher/routes/TeacherCoursesRoute"),
          },
          {
            path: "courses/:courseId",
            handle: { title: "Lớp phụ trách" },
            lazy: () => import("@/features/teacher/routes/TeacherCourseLayout"),
            children: [
              {
                index: true,
                handle: { title: "Tổng quan lớp" },
                lazy: () => import("@/features/teacher/routes/TeacherCourseOverviewRoute"),
              },
              {
                path: "students",
                handle: { title: "Sinh viên" },
                lazy: () => import("@/features/teacher/routes/TeacherCourseStudentsRoute"),
              },
              {
                path: "students/import",
                handle: { title: "Nhập sinh viên" },
                lazy: () => import("@/features/teacher/routes/TeacherStudentImportRoute"),
              },
              {
                path: "settings",
                handle: { title: "Cài đặt lớp" },
                lazy: () => import("@/features/teacher/routes/TeacherCourseSettingsRoute"),
              },
              {
                path: "teams",
                handle: { title: "Nhóm đồ án" },
                lazy: () => import("@/features/teacher/routes/TeacherCourseTeamsRoute"),
              },
              {
                path: "teams/:teamId",
                handle: { title: "Chi tiết nhóm" },
                lazy: () => import("@/features/teacher/routes/TeacherTeamDetailRoute"),
              },
              {
                path: "oversight",
                handle: { title: "Giám sát" },
                lazy: () => import("@/features/teacher/routes/TeacherCourseOversightRoute"),
              },
            ],
          },
        ],
      },
      {
        path: "/notifications",
        handle: { title: "Trung tâm Thông báo" },
        lazy: () => import("@/features/notifications/routes/NotificationsRoute"),
      },
      {
        path: "/settings/profile",
        handle: { title: "Cài đặt Cá nhân & Tích hợp" },
        lazy: () => import("@/features/notifications/routes/SettingsProfileRoute"),
      },
      {
        path: "/settings/integrations",
        handle: { title: "Cài đặt Cá nhân & Tích hợp" },
        lazy: () => import("@/features/notifications/routes/SettingsIntegrationsRoute"),
      },
      {
        path: "/settings/integrations/github/callback",
        handle: { title: "Liên kết GitHub" },
        lazy: () => import("@/features/notifications/routes/GitHubAuthorizationCallbackRoute"),
      },
      {
        path: "/settings/integrations/github/setup",
        handle: { title: "Cài GitHub App" },
        lazy: () => import("@/features/notifications/routes/GitHubInstallationCallbackRoute"),
      },
      {
        path: "/settings/security",
        handle: { title: "Cài đặt Cá nhân & Tích hợp" },
        lazy: () => import("@/features/notifications/routes/SettingsSecurityRoute"),
      },
      { path: "*", lazy: () => import("@/app/router/NotFoundRoute") },
    ] }],
  },
];

export const appRouter = createBrowserRouter(appRoutes);
