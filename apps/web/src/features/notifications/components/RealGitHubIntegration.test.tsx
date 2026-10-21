import { StrictMode } from "react";
import { screen, waitFor, type RenderOptions } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  githubAccountView,
  githubErrorMessage,
  RealGitHubIntegration,
} from "@/features/notifications/components/RealGitHubIntegration";
import { Component as AuthorizationCallback } from "@/features/notifications/routes/GitHubAuthorizationCallbackRoute";
import { Component as InstallationCallback } from "@/features/notifications/routes/GitHubInstallationCallbackRoute";
import { ApiError } from "@/lib/api/errors";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import {
  buildGitHubAccount,
  buildInstallation,
  buildRepository,
  buildUnlinkedGitHubAccount,
  integrationHandlers,
  type IntegrationCall,
  type IntegrationFixture,
} from "@/test/integrationHandlers";
import { leaderTestSession, renderApp } from "@/test/render";

afterEach(() => vi.unstubAllGlobals());

function setup(
  fixture: IntegrationFixture,
  element = <RealGitHubIntegration />,
  route = "/settings/integrations",
  options: RenderOptions = {},
) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,integration");
  const calls: IntegrationCall[] = [];
  server.use(...integrationHandlers({ ...fixture, calls }), ...createAuthHandlers("default", createMemoryRepository("default")));
  const view = renderApp(element, {
    ...options,
    route,
    session: leaderTestSession,
    routes: [
      { path: "/settings/integrations", element },
      { path: "/settings/integrations/github/callback", element },
      { path: "/settings/integrations/github/setup", element },
    ],
  });
  return { calls, ...view };
}

function stubLocationAssign() {
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  return assign;
}

describe("githubErrorMessage", () => {
  const error = (status: number, code: string | null, message = "server") => new ApiError({ status, code, message });

  it.each([
    [error(503, "GITHUB_UNAVAILABLE"), "Máy chủ chưa bật kết nối GitHub."],
    [error(409, "GITHUB_CONSENT_CONFLICT"), "Phiên cấp quyền đã thay đổi, vui lòng thử lại."],
    [error(409, "GITHUB_REAUTH_REQUIRED"), "Cần cấp quyền GitHub lại."],
    [error(429, "GITHUB_RATE_LIMITED"), "GitHub đang giới hạn yêu cầu, thử lại sau."],
    [error(403, "GITHUB_ACCESS_DENIED"), "GitHub từ chối truy cập."],
    [error(400, "INVALID_REQUEST"), "Phiên cấp quyền đã hết hạn hoặc không hợp lệ."],
    [error(500, "SOMETHING_ELSE", "Lỗi máy chủ"), "Lỗi máy chủ"],
    [new Error("mạng"), "mạng"],
  ])("maps %#", (input, expected) => {
    expect(githubErrorMessage(input)).toBe(expected);
  });
});

describe("githubAccountView", () => {
  it("only treats LINKED as linked and falls back to unlinked for unknown values", () => {
    expect(githubAccountView(buildGitHubAccount())).toBe("linked");
    expect(githubAccountView(buildGitHubAccount({ authorization_status: "REAUTH_REQUIRED" }))).toBe("reauth");
    expect(githubAccountView(buildGitHubAccount({ authorization_status: "REVOKED" }))).toBe("revoked");
    expect(githubAccountView(buildGitHubAccount({ authorization_status: "NOT_AUTHORIZED" }))).toBe("revoked");
    expect(githubAccountView(buildGitHubAccount({ status: "REVOKED" }))).toBe("unlinked");
    expect(githubAccountView(buildGitHubAccount({ authorization_status: "WEIRD" as never }))).toBe("unlinked");
  });
});

describe("RealGitHubIntegration", () => {
  it("shows the linked account with a disconnect button", async () => {
    setup({ account: buildGitHubAccount() });

    expect(await screen.findByText("Đã liên kết @octocat")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ngắt liên kết/ })).toBeInTheDocument();
  });

  it("asks to re-authorise when authorization needs renewal", async () => {
    setup({ account: buildGitHubAccount({ authorization_status: "REAUTH_REQUIRED" }) });

    expect(await screen.findByText("Cần cấp quyền lại")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cấp quyền lại/ })).toBeInTheDocument();
  });

  it("tells the user access was revoked", async () => {
    setup({ account: buildGitHubAccount({ authorization_status: "REVOKED" }) });

    expect(await screen.findByText("Quyền GitHub đã bị thu hồi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cấp quyền lại/ })).toBeInTheDocument();
  });

  it("starts authorization and redirects to the GitHub URL", async () => {
    const assign = stubLocationAssign();
    const { calls } = setup({ account: buildUnlinkedGitHubAccount() });

    expect(await screen.findByText("Chưa liên kết GitHub")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /Liên kết GitHub/ }));

    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("https://github.com/login/oauth/authorize?client_id=app&state=s1"),
    );
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
  });

  it("switches to the unlinked state after confirming disconnect", async () => {
    const user = userEvent.setup();
    setup({ account: buildGitHubAccount() });

    await user.click(await screen.findByRole("button", { name: /^Ngắt liên kết$/ }));
    await user.click(await screen.findByRole("button", { name: /Xác nhận ngắt liên kết/ }));

    expect(await screen.findByText("Chưa liên kết GitHub")).toBeInTheDocument();
  });

  it("shows the unavailable message when the server has GitHub disabled", async () => {
    setup({ account: buildGitHubAccount(), appEnabled: false });

    expect(await screen.findByText("Máy chủ chưa bật kết nối GitHub.")).toBeInTheDocument();
  });

  it("toasts the mapped error when starting authorization fails", async () => {
    const { calls } = setup({ account: buildUnlinkedGitHubAccount() });
    expect(await screen.findByText("Chưa liên kết GitHub")).toBeInTheDocument();
    server.use(
      ...integrationHandlers({
        account: buildUnlinkedGitHubAccount(),
        failWith: { status: 429, code: "GITHUB_RATE_LIMITED", message: "x" },
        calls,
      }),
    );

    await userEvent.setup().click(screen.getByRole("button", { name: /Liên kết GitHub/ }));

    expect(await screen.findByText("GitHub đang giới hạn yêu cầu, thử lại sau.")).toBeInTheDocument();
  });
});

describe("GitHubAuthorizationCallbackRoute", () => {
  const callbackUrl = (query: string) => `/settings/integrations/github/callback?${query}`;

  it("completes exactly once with code and state, then returns to settings", async () => {
    const { calls, router } = setup(
      { account: buildUnlinkedGitHubAccount() },
      <AuthorizationCallback />,
      callbackUrl("code=c1&state=s1"),
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/integrations"));
    const posts = calls.filter((call) => call.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({ code: "c1", state: "s1" });
  });

  it("still completes only once when StrictMode runs the effect twice", async () => {
    const { calls, router } = setup(
      { account: buildUnlinkedGitHubAccount() },
      <AuthorizationCallback />,
      callbackUrl("code=c1&state=s1"),
      { wrapper: StrictMode },
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/integrations"));
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
  });

  it("does not call the API when the user cancelled on GitHub", async () => {
    const { calls } = setup(
      { account: buildUnlinkedGitHubAccount() },
      <AuthorizationCallback />,
      callbackUrl("error=access_denied&state=s1"),
    );

    expect(await screen.findByText("Bạn đã hủy cấp quyền GitHub.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("rejects a callback missing code or state without calling the API", async () => {
    const { calls } = setup({ account: buildUnlinkedGitHubAccount() }, <AuthorizationCallback />, callbackUrl("code=c1"));

    expect(await screen.findByText("Liên kết callback không hợp lệ.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("shows the mapped error and lets the user start over when complete fails", async () => {
    const assign = stubLocationAssign();
    const { calls } = setup(
      { account: buildUnlinkedGitHubAccount(), failWith: { status: 400, code: "INVALID_REQUEST", message: "x" } },
      <AuthorizationCallback />,
      callbackUrl("code=c1&state=s1"),
    );

    expect(await screen.findByText("Phiên cấp quyền đã hết hạn hoặc không hợp lệ.")).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);

    server.use(...integrationHandlers({ account: buildUnlinkedGitHubAccount(), calls }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Thử lại liên kết" }));
    await waitFor(() => expect(assign).toHaveBeenCalled());
  });
});

describe("GitHub App card", () => {
  const repos = (count: number) =>
    Array.from({ length: count }, (_, index) =>
      buildRepository({ repository_id: `repo-${index}`, full_name: `utask-org/repo-${index}`, private: index === 0 }),
    );

  it("disables installation and asks to link GitHub first when the account is not ACTIVE", async () => {
    const { calls } = setup({ account: buildUnlinkedGitHubAccount(), installations: [buildInstallation()] });

    expect(await screen.findByText("Cần liên kết GitHub trước.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cài GitHub App" })).toBeDisabled();
    expect(calls.some((call) => call.path.endsWith("/installations"))).toBe(false);
  });

  it("lists installations with account and repository selection", async () => {
    setup({
      account: buildGitHubAccount(),
      installations: [
        buildInstallation(),
        buildInstallation({ installation_id: "inst-2", account: { id: "3", login: "octocat", type: "User" }, repository_selection: "all" }),
      ],
    });

    expect(await screen.findByText("utask-org (Organization)")).toBeInTheDocument();
    expect(screen.getByText("Repo được chọn")).toBeInTheDocument();
    expect(screen.getByText("octocat (User)")).toBeInTheDocument();
    expect(screen.getByText("Tất cả repo")).toBeInTheDocument();
  });

  it("shows an empty state when no installation exists", async () => {
    setup({ account: buildGitHubAccount(), installations: [] });

    expect(await screen.findByText("Chưa cài GitHub App cho tài khoản/tổ chức nào.")).toBeInTheDocument();
  });

  it("opens repositories with a Private label and loads page 2 on demand", async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      account: buildGitHubAccount(),
      installations: [buildInstallation()],
      repositories: { "inst-1": repos(3) },
      pageSize: 2,
    });

    await user.click(await screen.findByText("utask-org (Organization)"));
    expect(await screen.findByText("utask-org/repo-0")).toBeInTheDocument();
    expect(screen.getByText("Private")).toBeInTheDocument();
    expect(screen.queryByText("utask-org/repo-2")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Tải thêm" }));

    expect(await screen.findByText("utask-org/repo-2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tải thêm" })).not.toBeInTheDocument();
    expect(calls.filter((call) => call.path.endsWith("/repositories")).map((call) => call.search)).toEqual([
      "?page=1&per_page=100",
      "?page=2&per_page=100",
    ]);
  });

  it("redirects to the installation URL when installing", async () => {
    const assign = stubLocationAssign();
    setup({ account: buildGitHubAccount(), installations: [] });

    await userEvent.setup().click(await screen.findByRole("button", { name: "Cài/cập nhật GitHub App" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://github.com/apps/utask/installations/new?state=s2"));
  });
});

describe("GitHubInstallationCallbackRoute", () => {
  const setupUrl = (query: string) => `/settings/integrations/github/setup?${query}`;
  const full = "state=s2&installation_id=7&setup_action=install";

  it("completes once and returns to settings when the installation is ACTIVE", async () => {
    const { calls, router } = setup(
      { account: buildGitHubAccount() },
      <InstallationCallback />,
      setupUrl(full),
      { wrapper: StrictMode },
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/integrations"));
    const posts = calls.filter((call) => call.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toEqual({ state: "s2", installation_id: "7", setup_action: "install" });
  });

  it("shows a pending message when the organisation owner has not approved", async () => {
    const { router } = setup(
      { account: buildGitHubAccount(), installationComplete: { status: "PENDING_APPROVAL", installation_id: "7" } },
      <InstallationCallback />,
      setupUrl(full),
    );

    expect(await screen.findByText("Yêu cầu cài đặt đang chờ chủ tổ chức duyệt.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/settings/integrations/github/setup");
  });

  it("does not call the API for setup_action=request without installation_id", async () => {
    const { calls } = setup(
      { account: buildGitHubAccount() },
      <InstallationCallback />,
      setupUrl("state=s2&setup_action=request"),
    );

    expect(await screen.findByText("Đã gửi yêu cầu cài đặt, chờ chủ tổ chức duyệt.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it.each([
    ["missing state", "installation_id=7&setup_action=install"],
    ["unknown setup_action", "state=s2&installation_id=7&setup_action=bogus"],
    ["missing installation_id", "state=s2&setup_action=install"],
  ])("rejects %s without calling the API", async (_name, query) => {
    const { calls } = setup({ account: buildGitHubAccount() }, <InstallationCallback />, setupUrl(query));

    expect(await screen.findByText("Liên kết callback không hợp lệ.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("shows the mapped error when complete fails", async () => {
    setup(
      { account: buildGitHubAccount(), failWith: { status: 409, code: "GITHUB_CONSENT_CONFLICT", message: "x" } },
      <InstallationCallback />,
      setupUrl(full),
    );

    expect(await screen.findByText("Phiên cấp quyền đã thay đổi, vui lòng thử lại.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại cài đặt" })).toBeInTheDocument();
  });
});
