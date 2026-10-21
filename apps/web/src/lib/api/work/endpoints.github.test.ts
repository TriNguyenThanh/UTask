import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  confirmTaskGitHubLink,
  createTaskGitHubLink,
  declareGitHubUsername,
  deleteTaskGitHubLink,
  getProjectRepository,
  listTaskGitHubLinks,
  RepositoryPendingTimeoutError,
  requestGitHubVerification,
  selectProjectRepository,
  selectProjectRepositoryAndWait,
} from "@/lib/api/work/endpoints.github";
import { server } from "@/mocks/server";
import { buildProject, buildProjectMember, buildProjectRepository, buildTaskGitHubLink, workHandlers, type WorkCall, type WorkFixture } from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function use(fixture: Partial<WorkFixture> = {}) {
  const calls: WorkCall[] = [];
  server.use(
    ...workHandlers({
      projects: [buildProject({ id: "p/1" })],
      members: { "p/1": [buildProjectMember({ user_id: "u1" })] },
      ...fixture,
      calls,
    }),
  );
  return calls;
}

describe("declareGitHubUsername", () => {
  it("PATCHes only github_username to the encoded member path, without Idempotency-Key", async () => {
    const calls = use();

    const result = await declareGitHubUsername(client, "p/1", "u1", "octocat");

    expect(result).toEqual({ user_id: "u1", github_username: "octocat", is_github_verified: false });
    expect(calls[0]).toMatchObject({
      method: "PATCH",
      path: "/projects/p/1/members/u1/github/",
      body: { github_username: "octocat" },
      idempotencyKey: null,
    });
  });

  it("surfaces the server field errors of a 400", async () => {
    server.use(
      http.patch("/api/work/projects/p1/members/u1/github/", () =>
        HttpResponse.json(
          {
            success: false,
            message: "Dữ liệu đầu vào không hợp lệ.",
            data: null,
            error: { code: "VALIDATION_ERROR", details: [{ field: "github_username", issue: "Vui lòng nhập tên." }] },
          },
          { status: 400 },
        ),
      ),
    );

    const error = await declareGitHubUsername(client, "p1", "u1", "").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, code: "VALIDATION_ERROR", fieldErrors: { github_username: ["Vui lòng nhập tên."] } });
  });

  it("keeps INVALID_OPERATION from a read-only project", async () => {
    use({ projects: [buildProject({ id: "p/1", archived_at: "2026-10-01T00:00:00Z" })] });

    await expect(declareGitHubUsername(client, "p/1", "u1", "octocat")).rejects.toMatchObject({
      status: 400,
      code: "INVALID_OPERATION",
    });
  });
});

describe("requestGitHubVerification", () => {
  it("POSTs without a body and forwards the optional Idempotency-Key", async () => {
    const calls = use();

    const result = await requestGitHubVerification(client, "p/1", "u1", "key-1");

    expect(result.user_id).toBe("u1");
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/projects/p/1/members/u1/github/request-verification/",
      body: null,
      idempotencyKey: "key-1",
    });
  });

  it("omits the header when no key is given", async () => {
    const calls = use();

    await requestGitHubVerification(client, "p/1", "u1");

    expect(calls[0]?.idempotencyKey).toBeNull();
  });

  it("propagates a 403 for non-leaders", async () => {
    use({ githubError: { status: 403, code: "PERMISSION_DENIED", message: "Không có quyền." } });

    await expect(requestGitHubVerification(client, "p/1", "u1")).rejects.toMatchObject({ status: 403, code: "PERMISSION_DENIED" });
  });
});

const INPUT = { githubRepoId: "42", operationId: "op-1", expectedGeneration: 0 };
const noSleep = () => Promise.resolve();

describe("getProjectRepository", () => {
  it("returns an all-null record for a project without a repository", async () => {
    use();
    const result = await getProjectRepository(client, "p/1");
    expect(result).toMatchObject({ github_repo_id: null, status: null });
  });

  it("propagates 404", async () => {
    use();
    await expect(getProjectRepository(client, "missing")).rejects.toMatchObject({ status: 404 });
  });
});

describe("selectProjectRepository", () => {
  it("sends exactly the contract keys and uses operation_id as Idempotency-Key", async () => {
    const calls = use();

    const result = await selectProjectRepository(client, "p/1", INPUT);

    expect(result).toMatchObject({ status: "CONNECTED", github_repo_name: "repo-42", operation_id: "op-1" });
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/projects/p/1/github/repository/",
      idempotencyKey: "op-1",
      body: { github_repo_id: "42", operation_id: "op-1", expected_connection_generation: 0 },
    });
    expect(Object.keys(calls[0]?.body ?? {}).sort()).toEqual(["expected_connection_generation", "github_repo_id", "operation_id"]);
  });

  it("rejects a stale generation with 409", async () => {
    use({ repositories: { "p/1": buildProjectRepository({ connection_generation: 3 }) } });
    await expect(selectProjectRepository(client, "p/1", INPUT)).rejects.toMatchObject({ status: 409, code: "VERSION_CONFLICT" });
  });

  it("propagates 503 INTEGRATION_UNAVAILABLE", async () => {
    use({ repositoryError: { status: 503, code: "INTEGRATION_UNAVAILABLE", message: "Chưa sẵn sàng." } });
    await expect(selectProjectRepository(client, "p/1", INPUT)).rejects.toMatchObject({ status: 503, code: "INTEGRATION_UNAVAILABLE" });
  });
});

describe("selectProjectRepositoryAndWait", () => {
  it("returns immediately when the first answer is final", async () => {
    const calls = use();
    const result = await selectProjectRepositoryAndWait(client, "p/1", INPUT, { sleep: noSleep });
    expect(result.status).toBe("CONNECTED");
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(0);
  });

  it("polls while PENDING and waits intervalMs between polls", async () => {
    const calls = use({ repositoryPendingPolls: 2 });
    const waits: number[] = [];

    const result = await selectProjectRepositoryAndWait(client, "p/1", INPUT, {
      intervalMs: 50,
      sleep: (ms) => {
        waits.push(ms);
        return Promise.resolve();
      },
    });

    expect(result.status).toBe("CONNECTED");
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(2);
    expect(waits).toEqual([50, 50]);
  });

  it("stops when another operation took over", async () => {
    use({
      repositories: { "p/1": buildProjectRepository({ status: "PENDING", operation_id: "other", connection_generation: 0 }) },
    });
    server.use(
      http.post("/api/work/projects/p/1/github/repository/", () =>
        HttpResponse.json({
          success: true,
          message: "OK",
          data: buildProjectRepository({ project_id: "p/1", status: "PENDING", operation_id: "other" }),
          meta: null,
          error: null,
        }),
      ),
    );

    const result = await selectProjectRepositoryAndWait(client, "p/1", INPUT, { sleep: noSleep });

    expect(result.operation_id).toBe("other");
  });

  it("throws RepositoryPendingTimeoutError after maxPolls", async () => {
    const calls = use({ repositoryPendingPolls: 99 });

    await expect(selectProjectRepositoryAndWait(client, "p/1", INPUT, { maxPolls: 3, sleep: noSleep })).rejects.toBeInstanceOf(
      RepositoryPendingTimeoutError,
    );
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(3);
  });
});

describe("task GitHub links", () => {
  it("lists every link of the task, including soft-deleted ones", async () => {
    use({
      githubLinks: [
        buildTaskGitHubLink({ id: "a", task_id: "t1" }),
        buildTaskGitHubLink({ id: "b", task_id: "t1", deleted_at: "2026-10-01T00:00:00Z" }),
        buildTaskGitHubLink({ id: "c", task_id: "other" }),
      ],
    });
    const result = await listTaskGitHubLinks(client, "t1");
    expect(result.map((link) => link.id)).toEqual(["a", "b"]);
  });

  it("creates with the contract body and forwards the Idempotency-Key", async () => {
    const calls = use();

    const link = await createTaskGitHubLink(client, "t1", { linkType: "BRANCH", githubRefId: "feature/x" }, "key-1");

    expect(link).toMatchObject({ task_id: "t1", link_type: "BRANCH", github_ref_id: "feature/x", confirmation_status: "PENDING" });
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/tasks/t1/github-links/",
      idempotencyKey: "key-1",
      body: { link_type: "BRANCH", github_ref_id: "feature/x" },
    });
  });

  it("sends a PR ref verbatim and lets the server normalise it", async () => {
    const calls = use();

    const link = await createTaskGitHubLink(client, "t1", { linkType: "PULL_REQUEST", githubRefId: "#012" }, "key-1");

    expect(calls[0]?.body).toEqual({ link_type: "PULL_REQUEST", github_ref_id: "#012" });
    expect(link.github_ref_id).toBe("12");
  });

  it("surfaces a 400 for an invalid PR number", async () => {
    use();
    await expect(createTaskGitHubLink(client, "t1", { linkType: "PULL_REQUEST", githubRefId: "abc" }, "k")).rejects.toMatchObject({
      status: 400,
      code: "VALIDATION_ERROR",
    });
  });

  it("confirms with a required Idempotency-Key and no body", async () => {
    const calls = use({ githubLinks: [buildTaskGitHubLink({ id: "l/1", task_id: "t1", is_verified: true })] });

    const link = await confirmTaskGitHubLink(client, "t1", "l/1", "key-2");

    expect(link.confirmation_status).toBe("CONFIRMED");
    expect(calls[0]).toMatchObject({ method: "POST", path: "/tasks/t1/github-links/l/1/confirm/", body: null, idempotencyKey: "key-2" });
  });

  it("propagates a refusal to confirm an unverified link", async () => {
    use({ githubLinks: [buildTaskGitHubLink({ id: "l1", task_id: "t1", is_verified: false })] });
    await expect(confirmTaskGitHubLink(client, "t1", "l1", "k")).rejects.toMatchObject({ status: 400, code: "INVALID_OPERATION" });
  });

  it("deletes a link and returns its id; unknown link is 404", async () => {
    const calls = use({ githubLinks: [buildTaskGitHubLink({ id: "l1", task_id: "t1" })] });

    await expect(deleteTaskGitHubLink(client, "t1", "l1")).resolves.toEqual({ unlinked_id: "l1" });
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/tasks/t1/github-links/l1/", idempotencyKey: null });
    await expect(deleteTaskGitHubLink(client, "t1", "l1")).rejects.toMatchObject({ status: 404 });
  });

  it("propagates 503 INTEGRATION_UNAVAILABLE", async () => {
    use({ githubLinksError: { status: 503, code: "INTEGRATION_UNAVAILABLE", message: "x" } });
    await expect(listTaskGitHubLinks(client, "t1")).rejects.toMatchObject({ status: 503, code: "INTEGRATION_UNAVAILABLE" });
  });
});
