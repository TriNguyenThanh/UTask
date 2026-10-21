import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  completeGitHubAuthorization,
  completeGitHubInstallation,
  getGitHubAccount,
  listGitHubInstallations,
  listGitHubRepositories,
  startGitHubAuthorization,
  startGitHubInstallation,
  unlinkGitHubAccount,
} from "@/lib/api/integration/endpoints";
import { server } from "@/mocks/server";
import {
  buildGitHubAccount,
  buildInstallation,
  buildRepository,
  integrationHandlers,
  type IntegrationCall,
  type IntegrationFixture,
} from "@/test/integrationHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function use(fixture: Partial<IntegrationFixture> = {}) {
  const calls: IntegrationCall[] = [];
  server.use(...integrationHandlers({ account: buildGitHubAccount(), ...fixture, calls }));
  return calls;
}

describe("Integration GitHub endpoints", () => {
  it("returns the account DTO", async () => {
    use();
    await expect(getGitHubAccount(client)).resolves.toEqual(buildGitHubAccount());
  });

  it("unlinks with DELETE and returns the unlinked account", async () => {
    const calls = use();
    const account = await unlinkGitHubAccount(client);

    expect(account.status).toBe("UNLINKED");
    expect(calls[0]).toMatchObject({ method: "DELETE", path: "/api/integrations/api/v1/github/account" });
  });

  it("sends start requests without a body, query or Content-Type", async () => {
    const calls = use();

    const authorization = await startGitHubAuthorization(client);
    const installation = await startGitHubInstallation(client);

    expect(authorization.authorization_url).toContain("github.com/login/oauth/authorize");
    expect(installation.installation_url).toContain("github.com/apps/");
    for (const call of calls) {
      expect(call).toMatchObject({ method: "POST", body: null, search: "", contentType: null });
    }
  });

  it("sends exactly the keys each complete route accepts", async () => {
    const calls = use({ account: buildGitHubAccount({ status: "UNLINKED", authorization_status: "NOT_AUTHORIZED" }) });

    const account = await completeGitHubAuthorization(client, { code: "c", state: "s" });
    const installation = await completeGitHubInstallation(client, { state: "s", installation_id: "7", setup_action: "install" });

    expect(account.status).toBe("LINKED");
    expect(installation.status).toBe("ACTIVE");
    expect(calls[0]?.body).toEqual({ code: "c", state: "s" });
    expect(calls[1]?.body).toEqual({ state: "s", installation_id: "7", setup_action: "install" });
  });

  it("returns PENDING_APPROVAL when the organisation owner has not approved yet", async () => {
    use({ installationComplete: { status: "PENDING_APPROVAL", installation_id: "7" } });

    await expect(
      completeGitHubInstallation(client, { state: "s", installation_id: "7", setup_action: "request" }),
    ).resolves.toEqual({ status: "PENDING_APPROVAL", installation_id: "7" });
  });

  it("builds pagination queries and encodes the installation id", async () => {
    const calls = use({
      installations: [buildInstallation()],
      repositories: { "a/b": [buildRepository()] },
    });

    await listGitHubInstallations(client);
    await listGitHubInstallations(client, { page: 3, perPage: 20 });
    const repos = await listGitHubRepositories(client, "a/b", { page: 2 });

    expect(calls.map((call) => call.search)).toEqual(["?page=1&per_page=100", "?page=3&per_page=20", "?page=2&per_page=100"]);
    expect(calls[2]?.path).toBe("/api/integrations/api/v1/github/installations/a%2Fb/repositories");
    expect(repos.items).toEqual([]);
  });

  it("returns pages with next_page", async () => {
    use({ installations: [buildInstallation(), buildInstallation({ installation_id: "inst-2" })], pageSize: 1 });

    const first = await listGitHubInstallations(client);
    const second = await listGitHubInstallations(client, { page: 2 });

    expect(first.next_page).toBe(2);
    expect(second).toMatchObject({ next_page: null, items: [{ installation_id: "inst-2" }] });
  });

  it("throws an ApiError with GITHUB_UNAVAILABLE when the App is disabled", async () => {
    use({ appEnabled: false });

    const error = await getGitHubAccount(client).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: "GITHUB_UNAVAILABLE" });
  });

  it("throws on 401 NOT_AUTHENTICATED", async () => {
    use({ failWith: { status: 401, code: "NOT_AUTHENTICATED", message: "Chưa đăng nhập." } });

    await expect(startGitHubAuthorization(client)).rejects.toMatchObject({ status: 401, code: "NOT_AUTHENTICATED" });
  });
});
