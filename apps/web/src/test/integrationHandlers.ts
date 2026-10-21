import { http, HttpResponse, type HttpHandler } from "msw";

import type {
  GitHubAccountDto,
  GitHubInstallationDto,
  GitHubPageDto,
  GitHubRepositoryDto,
} from "@/lib/api/integration/dto";

const ROOT = "/api/integrations/api/v1/github";

export interface IntegrationCall {
  method: string;
  path: string;
  search: string;
  body: unknown;
  contentType: string | null;
}

export interface IntegrationFixture {
  account: GitHubAccountDto;
  installations?: GitHubInstallationDto[];
  /** Theo `installation_id`. */
  repositories?: Record<string, GitHubRepositoryDto[]>;
  /** Mặc định `true`. `false` → mọi route trả 503 `GITHUB_UNAVAILABLE`. */
  appEnabled?: boolean;
  /** Số item mỗi trang khi test phân trang (mặc định dùng `per_page` của request). */
  pageSize?: number;
  /** Kết quả của `installations/complete` (mặc định `ACTIVE` với installation đầu tiên). */
  installationComplete?: { status: "PENDING_APPROVAL"; installation_id: string } | null;
  /** Ép route trả lỗi này (áp dụng cho mọi route). */
  failWith?: { status: number; code: string; message: string };
  calls?: IntegrationCall[];
}

export function buildGitHubAccount(overrides: Partial<GitHubAccountDto> = {}): GitHubAccountDto {
  return {
    user_id: "user-1",
    status: "LINKED",
    authorization_status: "ACTIVE",
    github_user_id: "1001",
    github_username: "octocat",
    verified_at: "2026-10-20T00:00:00Z",
    linked_at: "2026-10-20T00:00:00Z",
    revoked_at: null,
    source_version: 1,
    ...overrides,
  };
}

export function buildUnlinkedGitHubAccount(overrides: Partial<GitHubAccountDto> = {}): GitHubAccountDto {
  return buildGitHubAccount({
    status: "UNLINKED",
    authorization_status: "NOT_AUTHORIZED",
    github_user_id: null,
    github_username: null,
    verified_at: null,
    linked_at: null,
    ...overrides,
  });
}

export function buildInstallation(overrides: Partial<GitHubInstallationDto> = {}): GitHubInstallationDto {
  return {
    installation_id: "inst-1",
    app_id: "app-1",
    account: { id: "2001", login: "utask-org", type: "Organization" },
    repository_selection: "selected",
    suspended_at: null,
    ...overrides,
  };
}

export function buildRepository(overrides: Partial<GitHubRepositoryDto> = {}): GitHubRepositoryDto {
  return { repository_id: "repo-1", name: "utask", full_name: "utask-org/utask", private: false, ...overrides };
}

function errorBody(code: string, message: string) {
  return { success: false, error: { code, message } };
}

function paginate<T>(items: T[], url: URL, pageSize?: number): GitHubPageDto<T> {
  const page = Number(url.searchParams.get("page") ?? "1");
  const perPage = pageSize ?? Number(url.searchParams.get("per_page") ?? "100");
  const slice = items.slice((page - 1) * perPage, page * perPage);
  return { items: slice, next_page: page * perPage < items.length ? page + 1 : null };
}

const COMPLETE_KEYS = {
  authorizations: ["code", "state"],
  installations: ["installation_id", "setup_action", "state"],
} as const;

export function integrationHandlers(fixture: IntegrationFixture): HttpHandler[] {
  let account = fixture.account;

  async function record(request: Request): Promise<{ body: unknown; text: string }> {
    const url = new URL(request.url);
    const text = await request.text();
    const body = text ? (JSON.parse(text) as unknown) : null;
    fixture.calls?.push({
      method: request.method,
      path: url.pathname,
      search: url.search,
      body,
      contentType: request.headers.get("Content-Type"),
    });
    return { body, text };
  }

  function gate(): Response | null {
    if (fixture.appEnabled === false) {
      return HttpResponse.json(errorBody("GITHUB_UNAVAILABLE", "GitHub chưa được bật."), { status: 503 });
    }
    if (fixture.failWith) {
      const { status, code, message } = fixture.failWith;
      return HttpResponse.json(errorBody(code, message), { status });
    }
    return null;
  }

  const invalid = () => HttpResponse.json(errorBody("INVALID_REQUEST", "Yêu cầu không hợp lệ."), { status: 400 });

  /** `start` từ chối mọi body và query. */
  async function start(request: Request, payload: unknown) {
    const { text } = await record(request);
    const blocked = gate();
    if (blocked) return blocked;
    if (text || new URL(request.url).search) return invalid();
    return HttpResponse.json({ success: true, data: payload });
  }

  async function complete(request: Request, kind: keyof typeof COMPLETE_KEYS, payload: () => unknown) {
    const { body } = await record(request);
    const blocked = gate();
    if (blocked) return blocked;
    const keys = body && typeof body === "object" ? Object.keys(body).sort() : [];
    if (keys.join(",") !== [...COMPLETE_KEYS[kind]].join(",")) return invalid();
    return HttpResponse.json({ success: true, data: payload() });
  }

  return [
    http.get(`${ROOT}/account`, async ({ request }) => {
      await record(request);
      return gate() ?? HttpResponse.json({ success: true, data: account });
    }),
    http.delete(`${ROOT}/account`, async ({ request }) => {
      await record(request);
      const blocked = gate();
      if (blocked) return blocked;
      account = buildUnlinkedGitHubAccount({ user_id: account.user_id, revoked_at: "2026-10-21T00:00:00Z" });
      return HttpResponse.json({ success: true, data: account });
    }),
    http.post(`${ROOT}/authorizations/start`, ({ request }) =>
      start(request, {
        authorization_url: "https://github.com/login/oauth/authorize?client_id=app&state=s1",
        expires_at: "2026-10-21T00:10:00Z",
      }),
    ),
    http.post(`${ROOT}/authorizations/complete`, ({ request }) =>
      complete(request, "authorizations", () => {
        account = buildGitHubAccount({ user_id: account.user_id });
        return account;
      }),
    ),
    http.post(`${ROOT}/installations/start`, ({ request }) =>
      start(request, {
        installation_url: "https://github.com/apps/utask/installations/new?state=s2",
        expires_at: "2026-10-21T00:10:00Z",
      }),
    ),
    http.post(`${ROOT}/installations/complete`, ({ request }) =>
      complete(
        request,
        "installations",
        () => fixture.installationComplete ?? { status: "ACTIVE", ...(fixture.installations?.[0] ?? buildInstallation()) },
      ),
    ),
    http.get(`${ROOT}/installations`, async ({ request }) => {
      await record(request);
      const blocked = gate();
      if (blocked) return blocked;
      return HttpResponse.json({
        success: true,
        data: paginate(fixture.installations ?? [], new URL(request.url), fixture.pageSize),
      });
    }),
    http.get(`${ROOT}/installations/:installationId/repositories`, async ({ request, params }) => {
      await record(request);
      const blocked = gate();
      if (blocked) return blocked;
      const items = fixture.repositories?.[String(params.installationId)] ?? [];
      return HttpResponse.json({ success: true, data: paginate(items, new URL(request.url), fixture.pageSize) });
    }),
  ];
}
