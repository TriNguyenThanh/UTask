import { http } from "msw";
import { describe, expect, it } from "vitest";

import {
  createGroup,
  issueGroupInviteCode,
  joinGroup,
  leaveGroup,
  patchGroup,
  removeMember,
  transferLeader,
} from "@/lib/api/classroom/endpoints";
import { createApiClient } from "@/lib/api/client";
import { server } from "@/mocks/server";
import { buildGroup, envelope, envelopeError } from "@/test/classroomHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });
const KEY = "11111111-1111-4111-8111-111111111111";

interface Seen {
  method: string;
  path: string;
  key: string | null;
  body: unknown;
}

function capture(method: "post" | "patch", path: string, data: unknown = buildGroup()) {
  const seen: Seen[] = [];
  const handler = http[method](path, async ({ request }) => {
    seen.push({ method: request.method, path: new URL(request.url).pathname, key: request.headers.get("Idempotency-Key"), body: await request.json() });
    return envelope(data);
  });
  server.use(handler);
  return seen;
}

describe("group commands", () => {
  it("createGroup posts class_id and name", async () => {
    const seen = capture("post", "/api/classroom/groups/");
    await createGroup(client, { classId: "c1", name: "Nhóm A", idempotencyKey: KEY });
    expect(seen).toEqual([{ method: "POST", path: "/api/classroom/groups/", key: KEY, body: { class_id: "c1", name: "Nhóm A" } }]);
  });

  it("joinGroup posts the code", async () => {
    const seen = capture("post", "/api/classroom/groups/join/");
    await joinGroup(client, { code: "ABC", idempotencyKey: KEY });
    expect(seen[0]).toMatchObject({ key: KEY, body: { code: "ABC" } });
  });

  it("patchGroup sends only the given fields", async () => {
    const seen = capture("patch", "/api/classroom/groups/g1/");
    await patchGroup(client, "g1", { version: 4, name: "Mới", idempotencyKey: KEY });
    expect(seen[0]).toMatchObject({ method: "PATCH", key: KEY, body: { version: 4, name: "Mới" } });
  });

  it("issueGroupInviteCode returns the one-time raw code and omits expires_at when not given", async () => {
    const seen = capture("post", "/api/classroom/groups/g1/invite-code/", { id: "g1", version: 5, code: "XYZ789", expires_at: "2030-01-01T00:00:00Z", enabled: true });
    const result = await issueGroupInviteCode(client, "g1", { version: 4, enabled: true, idempotencyKey: KEY });
    expect(result.code).toBe("XYZ789");
    expect(seen[0].body).toEqual({ version: 4, enabled: true });
  });

  it("leaveGroup posts version and reason without user_id", async () => {
    const seen = capture("post", "/api/classroom/groups/g1/leave/");
    await leaveGroup(client, "g1", { version: 2, reason: "Đổi nhóm", idempotencyKey: KEY });
    expect(seen[0]).toMatchObject({ key: KEY, body: { version: 2, reason: "Đổi nhóm" } });
  });

  it("transferLeader and removeMember post user_id", async () => {
    const transfer = capture("post", "/api/classroom/groups/g1/transfer-leader/");
    const remove = capture("post", "/api/classroom/groups/g1/remove-member/");
    await transferLeader(client, "g1", { version: 2, reason: "Bàn giao", userId: "u2", idempotencyKey: KEY });
    await removeMember(client, "g1", { version: 3, reason: "Không hoạt động", userId: "u3", idempotencyKey: KEY });
    expect(transfer[0].body).toEqual({ version: 2, reason: "Bàn giao", user_id: "u2" });
    expect(remove[0].body).toEqual({ version: 3, reason: "Không hoạt động", user_id: "u3" });
  });

  it("surfaces a version conflict as an ApiError with the backend code", async () => {
    server.use(http.post("/api/classroom/groups/g1/leave/", () => envelopeError(409, "VERSION_CONFLICT", "Nhóm học tập đã thay đổi. Vui lòng tải lại dữ liệu.")));
    await expect(leaveGroup(client, "g1", { version: 1, reason: "x", idempotencyKey: KEY })).rejects.toMatchObject({ status: 409, code: "VERSION_CONFLICT" });
  });

  it("surfaces 403 without retrying into a different result", async () => {
    server.use(http.post("/api/classroom/groups/g1/remove-member/", () => envelopeError(403, "PERMISSION_DENIED", "Bạn không có quyền.")));
    await expect(removeMember(client, "g1", { version: 1, reason: "x", userId: "u", idempotencyKey: KEY })).rejects.toMatchObject({ status: 403 });
  });
});
