import { Navigate, createBrowserRouter } from "react-router-dom";

import { AuthenticatedLayout } from "@/app/layouts/AuthenticatedLayout";
import { RequireAuth } from "@/app/router/RequireAuth";
import { RequireProjectManagePermission } from "@/features/projects/routes/RequireProjectManagePermission";
import { RouteError } from "@/app/router/RouteError";

export const appRouter = createBrowserRouter([
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
    path: "/reset-password",
    lazy: () => import("@/features/auth/routes/ResetPasswordRoute"),
    errorElement: <RouteError />,
  },
  {
    element: (
      <RequireAuth>
        <AuthenticatedLayout />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
    children: [
      { path: "/", element: <Navigate to="/my-work" replace /> },
      {
        path: "/my-work",
        handle: { crumb: "Trang Chủ" },
        lazy: () => import("@/features/my-work/routes/MyWorkRoute"),
      },
      {
        path: "/courses",
        lazy: () => import("@/features/courses/routes/CoursesRoute"),
      },
      {
        path: "/courses/:courseId/team",
        lazy: () => import("@/features/courses/routes/CourseTeamRoute"),
      },
      {
        path: "/projects",
        handle: { crumb: "Dự án" },
        lazy: () => import("@/features/projects/routes/ProjectsRoute"),
      },
      {
        path: "/projects/:projectId",
        lazy: () => import("@/features/projects/routes/ProjectWorkspaceLayout"),
        children: [
          { index: true, element: <Navigate to="backlog" replace /> },
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
        ],
      },
      {
        path: "/notifications",
        lazy: () => import("@/features/notifications/routes/NotificationsRoute"),
      },
      {
        path: "/settings/profile",
        lazy: () => import("@/features/notifications/routes/SettingsProfileRoute"),
      },
      {
        path: "/settings/integrations",
        lazy: () => import("@/features/notifications/routes/SettingsIntegrationsRoute"),
      },
      {
        path: "/settings/security",
        lazy: () => import("@/features/notifications/routes/SettingsSecurityRoute"),
      },
      { path: "*", lazy: () => import("@/app/router/NotFoundRoute") },
    ],
  },
]);