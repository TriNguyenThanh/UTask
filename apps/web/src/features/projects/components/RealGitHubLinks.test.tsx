import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { githubLinkErrorMessage, isValidGitHubRef, RealGitHubLinks } from "@/features/projects/components/RealGitHubLinks";
import { ApiError } from "@/lib/api/errors";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { leaderTestSession, renderApp } from "@/test/render";
import { buildProject, buildTaskGitHubLink, workHandlers, type WorkFixture } from "@/test/workHandlers";

function setup(fixture: Partial<WorkFixture> = {}, editable = true) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth,work");
  const calls: NonNullable<WorkFixture["calls"]> = [];
  const state: Partial<WorkFixture> = { githubLinks: [], ...fixture };
  server.use(
    ...workHandlers({ projects: [buildProject({ id: "project-1" })], ...state, calls }),
    ...createAuthHandlers("default", createMemoryRepository("default")),
  );
  const view = renderApp(<RealGitHubLinks taskId="task-1" projectId="project-1" editable={editable} />, {
    route: "/x",
    session: leaderTestSession,
  });
  return { calls, state, ...view };
}

describe("isValidGitHubRef", () => {
  it("requires a positive integer (optional #) only for pull requests", () => {
    expect(isValidGitHubRef("PULL_REQUEST", "12")).toBe(true);
    expect(isValidGitHubRef("PULL_REQUEST", "#12")).toBe(true);
    for (const bad of ["abc", "0", "#0", "1.5", "-3", ""]) expect(isValidGitHubRef("PULL_REQUEST", bad)).toBe(false);
    expect(isValidGitHubRef("BRANCH", "feature/x")).toBe(true);
    expect(isValidGitHubRef("COMMIT", "   ")).toBe(false);
    expect(isValidGitHubRef("BRANCH", "x".repeat(301))).toBe(false);
  });
});

describe("githubLinkErrorMessage", () => {
  it("explains 503 INTEGRATION_UNAVAILABLE (B34) and keeps other messages", () => {
    expect(githubLinkErrorMessage(new ApiError({ status: 503, code: "INTEGRATION_UNAVAILABLE", message: "x" }))).toBe(
      "Work chưa kết nối được Integration (chờ backend, B34).",
    );
    expect(githubLinkErrorMessage(new ApiError({ status: 400, code: "INVALID_OPERATION", message: "Từ máy chủ" }))).toBe("Từ máy chủ");
    expect(githubLinkErrorMessage("lạ")).toBe("lạ");
  });
});

describe("RealGitHubLinks", () => {
  it("lists live links, hides soft-deleted ones, and labels confirmation state", async () => {
    setup({
      githubLinks: [
        buildTaskGitHubLink({ id: "a", github_ref_id: "feature/login", github_title: "Login", github_url: "https://github.com/o/r/tree/feature/login" }),
        buildTaskGitHubLink({ id: "b", link_type: "PULL_REQUEST", github_ref_id: "12", confirmation_status: "CONFIRMED" }),
        buildTaskGitHubLink({ id: "c", github_ref_id: "gone", deleted_at: "2026-10-01T00:00:00Z" }),
      ],
    });

    expect(await screen.findByRole("link", { name: "Login" })).toHaveAttribute("href", "https://github.com/o/r/tree/feature/login");
    expect(screen.getByText("#12")).toBeInTheDocument();
    expect(screen.getByText("Chờ xác nhận")).toBeInTheDocument();
    expect(screen.getByText("Đã xác nhận")).toBeInTheDocument();
    expect(screen.queryByText("gone")).not.toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    setup();
    expect(await screen.findByText("Chưa có liên kết mã nguồn.")).toBeInTheDocument();
  });

  it("creates a link and refreshes the list", async () => {
    const user = userEvent.setup();
    const { calls } = setup();

    await screen.findByText("Chưa có liên kết mã nguồn.");
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "feature/new");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));

    const list = await screen.findByRole("list", { name: "Liên kết GitHub" });
    expect(within(list).getByText("feature/new")).toBeInTheDocument();
    expect(screen.getByLabelText("Mã tham chiếu GitHub")).toHaveValue("");
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ link_type: "BRANCH", github_ref_id: "feature/new" });
    expect(post?.idempotencyKey).toBeTruthy();
  });

  it("blocks an invalid PR number on the client without calling the API", async () => {
    const user = userEvent.setup();
    const { calls } = setup();

    await screen.findByText("Chưa có liên kết mã nguồn.");
    await user.selectOptions(screen.getByLabelText("Loại liên kết GitHub"), "PULL_REQUEST");
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "abc");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));

    expect(await screen.findByText("Mã Pull Request phải là số nguyên dương.")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("reuses the Idempotency-Key when the same input is retried after a failure", async () => {
    const user = userEvent.setup();
    const { calls, state } = setup({ repositoryNotConnected: true });

    await screen.findByText("Chưa có liên kết mã nguồn.");
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "main");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    const keys = calls.filter((c) => c.method === "POST").map((c) => c.idempotencyKey);
    expect(keys[0]).toBe(keys[1]);

    // Đổi input → key mới.
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "2");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(3));
    expect(calls.filter((c) => c.method === "POST")[2]?.idempotencyKey).not.toBe(keys[0]);
    expect(state.githubLinks).toHaveLength(0);
  });

  it("points to the Code tab when the project has no repository", async () => {
    const user = userEvent.setup();
    setup({ repositoryNotConnected: true });

    await screen.findByText("Chưa có liên kết mã nguồn.");
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "main");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));

    expect(await screen.findByText(/chưa được kết nối với kho lưu trữ/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở tab Code" })).toHaveAttribute("href", "/projects/project-1/code");
  });

  it("shows the B34 message on 503", async () => {
    const user = userEvent.setup();
    setup({ githubLinksError: { status: 503, code: "INTEGRATION_UNAVAILABLE", message: "x" } });
    // GET cũng 503: danh sách báo lỗi, form vẫn dùng được.
    expect(await screen.findByRole("alert")).toHaveTextContent("chờ backend, B34");
    await user.type(screen.getByLabelText("Mã tham chiếu GitHub"), "main");
    await user.click(screen.getByRole("button", { name: "Thêm liên kết" }));
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBe(2));
  });

  it("offers Xác nhận only for pending verified links, and confirming flips the badge", async () => {
    const user = userEvent.setup();
    const { calls } = setup({
      githubLinks: [
        buildTaskGitHubLink({ id: "v", github_ref_id: "verified", is_verified: true }),
        buildTaskGitHubLink({ id: "u", github_ref_id: "unverified", is_verified: false }),
      ],
    });

    await screen.findByText("verified");
    expect(screen.getAllByRole("button", { name: /^Xác nhận / })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Xác nhận verified" }));

    expect(await screen.findByText("Đã xác nhận")).toBeInTheDocument();
    const confirm = calls.find((c) => c.path.endsWith("/confirm/"));
    expect(confirm?.idempotencyKey).toBeTruthy();
    expect(confirm?.body).toBeNull();
  });

  it("deletes a link", async () => {
    const user = userEvent.setup();
    setup({ githubLinks: [buildTaskGitHubLink({ id: "a", github_ref_id: "old-branch" })] });

    await user.click(await screen.findByRole("button", { name: "Xóa liên kết old-branch" }));

    expect(await screen.findByText("Chưa có liên kết mã nguồn.")).toBeInTheDocument();
  });

  it("is read-only without edit permission", async () => {
    setup({ githubLinks: [buildTaskGitHubLink({ id: "a", github_ref_id: "main", is_verified: true })] }, false);

    await screen.findByText("main");
    expect(screen.queryByLabelText("Mã tham chiếu GitHub")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Xóa liên kết|Xác nhận /i })).not.toBeInTheDocument();
  });
});
