import { QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/features/auth/AuthProvider";
import type { AuthSession } from "@/features/auth/types";
import { LEADER_ID, MEMBER_ID, STUDENT_ID, TEACHER2_ID, TEACHER_ID } from "@/mocks/data/database";
import { appRoutes } from "@/app/router/router";
import { ApiClientProvider } from "@/lib/api/ApiClientProvider";
import { createTestQueryClient } from "@/lib/query/client";
export const leaderTestSession: AuthSession = {
  accessToken: `mock-access:${LEADER_ID}:test`,
  refreshToken: `mock-refresh:${LEADER_ID}`,
  user: {
    id: LEADER_ID,
    email: "leader@utask.test",
    display_name: "Nguyễn Hoàng Nam",
    global_role: "USER",
    capabilities: ["project:create"],
    roles: ["STUDENT"],
  },
};

export const memberTestSession: AuthSession = {
  accessToken: `mock-access:${MEMBER_ID}:test`,
  refreshToken: `mock-refresh:${MEMBER_ID}`,
  user: {
    id: MEMBER_ID,
    email: "member@utask.test",
    display_name: "Đặng Thảo Linh",
    global_role: "USER",
    capabilities: [],
    roles: ["STUDENT"],
  },
};

export const studentTestSession: AuthSession = {
  accessToken: `mock-access:${STUDENT_ID}:test`,
  refreshToken: `mock-refresh:${STUDENT_ID}`,
  user: {
    id: STUDENT_ID,
    email: "student@utask.test",
    display_name: "Lê Minh Khoa",
    global_role: "USER",
    capabilities: [],
    roles: ["STUDENT"],
  },
};

/** Sessions persisted before `roles` existed carry none and must stay plain students. */
export const legacyStudentTestSession: AuthSession = {
  ...studentTestSession,
  user: { ...studentTestSession.user, roles: undefined },
};

function teacherSession(userId: string, email: string, name: string): AuthSession {
  return {
    accessToken: `mock-access:${userId}:test`,
    refreshToken: `mock-refresh:${userId}`,
    user: { id: userId, email, display_name: name, global_role: "USER", capabilities: [], roles: ["TEACHER"] },
  };
}

/** teacher@utask.test — teaches SE330 (both classes) and IT3090. */
export const teacherTestSession = teacherSession(TEACHER_ID, "teacher@utask.test", "TS. Trần Minh Đức");
/** teacher2@utask.test — teaches CS402 only. */
export const teacher2TestSession = teacherSession(TEACHER2_ID, "teacher2@utask.test", "ThS. Lê Thị Mai");

export function renderApp(
  element: ReactElement,
  {
    route = "/",
    session = leaderTestSession,
    routes,
    ...options
  }: RenderOptions & {
    route?: string;
    session?: AuthSession | null;
    routes?: RouteObject[];
  } = {},
) {
  const queryClient = createTestQueryClient();
  const router = createMemoryRouter(
    routes ?? [{ path: "*", element }],
    { initialEntries: [route] },
  );

  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider initialSession={session} baseUrl="http://localhost">
        <ApiClientProvider baseUrl="http://localhost">
          <TooltipProvider>
            <RouterProvider router={router} />
            <Toaster richColors position="top-right" />
          </TooltipProvider>
        </ApiClientProvider>
      </AuthProvider>
    </QueryClientProvider>,
    options,
  );

  return { ...result, queryClient, router };
}

/** Renders the real route table (guards, layout, lazy routes) at `route`. */
export function renderAppRoutes(route: string, session: AuthSession | null) {
  return renderApp(<div />, { route, session, routes: appRoutes });
}
