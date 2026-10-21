import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  declareGitHubUsername,
  getProjectRepository,
  RepositoryPendingTimeoutError,
  requestGitHubVerification,
  selectProjectRepository,
  selectProjectRepositoryAndWait,
} from "@/lib/api/work/endpoints.github";
import { server } from "@/mocks/server";
import { buildProject, buildProjectMember, buildProjectRepository, workHandlers, type WorkCall, type WorkFixture } from "@/test/workHandlers";

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
