import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { declareGitHubUsername, requestGitHubVerification } from "@/lib/api/work/endpoints.github";
import { server } from "@/mocks/server";
import { buildProject, buildProjectMember, workHandlers, type WorkCall, type WorkFixture } from "@/test/workHandlers";

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
