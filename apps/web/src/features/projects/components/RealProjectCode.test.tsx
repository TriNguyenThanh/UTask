import { screen, waitFor, within } from "@testing-library/react";
import { http } from "msw";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { repositoryErrorMessage, repositoryStatusLabel } from "@/features/projects/components/RealProjectCode";
import { ApiError } from "@/lib/api/errors";
import { RepositoryPendingTimeoutError } from "@/lib/api/work/endpoints.github";
import { LEADER_ID, MEMBER_ID } from "@/mocks/data/database";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { buildClass, buildCourse, buildGroup, classroomHandlers, envelopeError } from "@/test/classroomHandlers";
import {
  buildGitHubAccount,
  buildInstallation,
  buildRepository,
  buildUnlinkedGitHubAccount,
  integrationHandlers,
  type IntegrationFixture,
} from "@/test/integrationHandlers";
import { leaderTestSession, memberTestSession, renderAppRoutes } from "@/test/render";
import { buildProject, buildProjectMember, buildProjectRepository, workHandlers, type WorkFixture } from "@/test/workHandlers";

function setup(
  work: Partial<WorkFixture> = {},
  session: typeof leaderTestSession | typeof memberTestSession = leaderTestSession,
  integration: IntegrationFixture | null = {
    account: buildGitHubAccount(),
    installations: [buildInstallation()],
    repositories: { "inst-1": [buildRepository({ repository_id: "42", full_name: "utask-org/nexus" })] },
  },
) {
  vi.stubEnv("VITE_REAL_SERVICES", integration ? "auth,classroom,work,integration" : "auth,classroom,work");
  server.use(
    ...workHandlers({
      projects: [buildProject({ id: "project-1" })],
      members: {
        "project-1": [
          buildProjectMember({ user_id: LEADER_ID, role: "LEADER", display_name: "Nam" }),
          buildProjectMember({ id: "pm-2", user_id: MEMBER_ID, role: "MEMBER", display_name: "Linh" }),
        ],
      },
      ...work,
    }),
    ...classroomHandlers({
      classes: [buildClass({ id: "class-1" })],
      courses: [buildCourse({ id: "course-1" })],
      groups: { "class-1": [buildGroup({ id: "group-1", class_section: "class-1" })] },
    }),
    ...(integration ? integrationHandlers(integration) : []),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  return renderAppRoutes("/projects/project-1/code", session);
}

describe("repositoryErrorMessage", () => {
  it("explains the missing Work adapter (B34) for 503 INTEGRATION_UNAVAILABLE", () => {
    const error = new ApiError({ status: 503, code: "INTEGRATION_UNAVAILABLE", message: "x" });
    expect(repositoryErrorMessage(error)).toBe("Work chưa kết nối được Integration (chờ backend, B34).");
  });

  it("maps any 409 to the reload message", () => {
    expect(repositoryErrorMessage(new ApiError({ status: 409, code: "VERSION_CONFLICT", message: "x" }))).toBe(
      "Kết nối repo đã thay đổi, đã tải lại.",
    );
  });

  it("keeps the timeout and unknown server messages", () => {
    expect(repositoryErrorMessage(new RepositoryPendingTimeoutError())).toBe("Kết nối đang chờ xử lý, tải lại sau.");
    expect(repositoryErrorMessage(new ApiError({ status: 422, code: "X", message: "Từ máy chủ" }))).toBe("Từ máy chủ");
    expect(repositoryErrorMessage("lạ")).toBe("lạ");
  });
});

describe("repositoryStatusLabel", () => {
  it("labels every status and treats null/unknown as not connected", () => {
    expect(repositoryStatusLabel("CONNECTED")).toBe("Đã kết nối");
    expect(repositoryStatusLabel("PENDING")).toBe("Đang kết nối");
    expect(repositoryStatusLabel("DISCONNECTED")).toBe("Chưa kết nối");
    expect(repositoryStatusLabel(null)).toBe("Chưa kết nối");
    expect(repositoryStatusLabel("WEIRD" as never)).toBe("Chưa kết nối");
  });
});

describe("RealProjectCode", () => {
  it("shows a connected repository with its link and branch", async () => {
    setup({
      repositories: {
        "project-1": buildProjectRepository({
          github_repo_owner: "utask",
          github_repo_name: "nexus",
          github_default_branch: "main",
          status: "CONNECTED",
          connection_generation: 1,
        }),
      },
    });

    const link = await screen.findByRole("link", { name: "utask/nexus" });
    expect(link).toHaveAttribute("href", "https://github.com/utask/nexus");
    expect(screen.getByText("Đã kết nối")).toBeInTheDocument();
    expect(screen.getByText("Nhánh mặc định: main")).toBeInTheDocument();
    expect(screen.getByText("Hoạt động commit/PR chưa có API (B36).")).toBeInTheDocument();
  });

  it("shows the empty state without a repository", async () => {
    setup();
    expect(await screen.findByText("Dự án chưa kết nối repository GitHub.")).toBeInTheDocument();
    expect(screen.getByText("Chưa kết nối")).toBeInTheDocument();
  });

  it("hides the picker button from members", async () => {
    setup({}, memberTestSession);
    await screen.findByText("Dự án chưa kết nối repository GitHub.");
    expect(screen.queryByRole("button", { name: "Chọn repository" })).not.toBeInTheDocument();
  });

  it("lets the leader pick a repository and shows it as connected", async () => {
    const calls: NonNullable<WorkFixture["calls"]> = [];
    const user = userEvent.setup();
    setup({ calls });

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));
    const dialog = await screen.findByRole("dialog", { name: "Chọn repository" });
    await user.click(await within(dialog).findByRole("button", { name: "utask-org" }));
    await user.click(await within(dialog).findByRole("button", { name: "Kết nối utask-org/nexus" }));

    expect(await screen.findByRole("link", { name: "utask/repo-42" })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ github_repo_id: "42", expected_connection_generation: 0 });
    expect(post?.idempotencyKey).toBe(post?.body?.operation_id);
  });

  it("waits through PENDING until the connection settles", async () => {
    const user = userEvent.setup();
    setup({ repositoryPendingPolls: 1 });

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));
    const dialog = await screen.findByRole("dialog", { name: "Chọn repository" });
    await user.click(await within(dialog).findByRole("button", { name: "utask-org" }));
    await user.click(await within(dialog).findByRole("button", { name: "Kết nối utask-org/nexus" }));

    expect(await screen.findByRole("link", { name: "utask/repo-42" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("Đã kết nối")).toBeInTheDocument();
  }, 10000);

  it("shows the B34 message when Work cannot reach Integration", async () => {
    const user = userEvent.setup();
    setup({ repositories: { "project-1": buildProjectRepository() } });
    server.use(
      http.post("/api/work/projects/project-1/github/repository/", () =>
        envelopeError(503, "INTEGRATION_UNAVAILABLE", "Chưa sẵn sàng."),
      ),
    );

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));
    const dialog = await screen.findByRole("dialog", { name: "Chọn repository" });
    await user.click(await within(dialog).findByRole("button", { name: "utask-org" }));
    await user.click(await within(dialog).findByRole("button", { name: "Kết nối utask-org/nexus" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Work chưa kết nối được Integration (chờ backend, B34).");
  });

  it("reloads and explains a 409 generation conflict", async () => {
    const user = userEvent.setup();
    setup({ repositories: { "project-1": buildProjectRepository({ connection_generation: 0 }) } });

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));
    const dialog = await screen.findByRole("dialog", { name: "Chọn repository" });
    await user.click(await within(dialog).findByRole("button", { name: "utask-org" }));
    // Thế hệ kết nối đổi ở phía server sau khi trang đã tải.
    server.use(
      ...workHandlers({
        projects: [buildProject({ id: "project-1" })],
        repositories: { "project-1": buildProjectRepository({ connection_generation: 5 }) },
      }),
    );
    await user.click(await within(dialog).findByRole("button", { name: "Kết nối utask-org/nexus" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Kết nối repo đã thay đổi, đã tải lại.");
  });

  it("asks to link GitHub first when the account is not active", async () => {
    const user = userEvent.setup();
    setup({}, leaderTestSession, { account: buildUnlinkedGitHubAccount() });

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));

    expect(await screen.findByText(/Cần liên kết GitHub trước/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở cài đặt tích hợp" })).toHaveAttribute("href", "/settings/integrations");
  });

  it("tells the leader to enable Integration when the service is off", async () => {
    const user = userEvent.setup();
    setup({}, leaderTestSession, null);

    await user.click(await screen.findByRole("button", { name: "Chọn repository" }));

    await waitFor(() => expect(screen.getByText("Cần bật Integration để chọn repo.")).toBeInTheDocument());
  });
});
