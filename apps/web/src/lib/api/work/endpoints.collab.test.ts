import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { uploadTaskAttachment } from "@/lib/api/work/attachmentUpload";
import {
  confirmAttachment,
  createComment,
  deleteAttachment,
  deleteComment,
  getAttachmentDownloadUrl,
  listProjectComments,
  listTaskActivities,
  listTaskAttachments,
  listTaskComments,
  patchComment,
  presignAttachment,
  uploadToStorage,
} from "@/lib/api/work/endpoints";
import { server } from "@/mocks/server";
import {
  buildActivity,
  buildAttachment,
  buildComment,
  buildDefaultStates,
  buildProject,
  STORAGE_ORIGIN,
  workHandlers,
  type WorkCall,
  type WorkFixture,
} from "@/test/workHandlers";

const client = createApiClient({ baseUrl: "http://localhost", getAccessToken: () => "token", onUnauthorized: () => undefined });

function setup(fixture: Partial<WorkFixture>) {
  const calls: WorkCall[] = [];
  const full = { projects: [buildProject()], states: buildDefaultStates(), calls, ...fixture };
  server.use(...workHandlers(full as WorkFixture));
  return { calls, full };
}

async function failureOf(promise: Promise<unknown>) {
  const error = await promise.then(() => null, (reason: unknown) => reason);
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("comments", () => {
  it("lists task comments and project comments separately", async () => {
    setup({
      comments: [
        buildComment({ id: "c1", task_id: "task-1" }),
        buildComment({ id: "c2", task_id: null, project_id: "project-1" }),
        buildComment({ id: "c3", task_id: "task-2" }),
      ],
    });
    expect((await listTaskComments(client, "task-1")).map((row) => row.id)).toEqual(["c1"]);
    expect((await listProjectComments(client, "project-1")).map((row) => row.id)).toEqual(["c2"]);
  });

  it("creates on a task or on a project with exactly one target and no Idempotency-Key", async () => {
    const { calls } = setup({});
    await createComment(client, { taskId: "task-1" }, { content: "Xin chào", mentionedUserIds: ["user-2"] });
    await createComment(client, { projectId: "project-1" }, { content: "Cả nhóm lưu ý", mentionedUserIds: [] });
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/comments/",
      idempotencyKey: null,
      body: { task_id: "task-1", content_html: "Xin chào", mentioned_user_ids: ["user-2"] },
    });
    expect(calls[1].body).toEqual({ project_id: "project-1", content_html: "Cả nhóm lưu ý", mentioned_user_ids: [] });
  });

  it("surfaces a mention outside the project as a 422 with the server's message", async () => {
    setup({ invalidMentions: ["outsider"] });
    const error = await failureOf(createComment(client, { taskId: "task-1" }, { content: "Hi", mentionedUserIds: ["outsider"] }));
    expect(error.status).toBe(422);
    expect(error.message).toContain("không thuộc phạm vi");
  });

  it("edits only your own comment and lets the leader delete someone else's", async () => {
    setup({ actorId: "me", comments: [buildComment({ id: "mine", user_id: "me" }), buildComment({ id: "theirs", user_id: "other" })] });
    expect((await patchComment(client, "mine", { content: "Sửa", mentionedUserIds: [] })).content_html).toBe("Sửa");
    expect((await failureOf(patchComment(client, "theirs", { content: "Sửa", mentionedUserIds: [] }))).status).toBe(403);
    expect((await failureOf(deleteComment(client, "theirs"))).status).toBe(403);

    setup({ actorId: "me", actorIsLeader: true, comments: [buildComment({ id: "theirs", user_id: "other" })] });
    expect((await deleteComment(client, "theirs")).deleted_at).not.toBeNull();
  });
});

describe("activities", () => {
  it("lists a task's history", async () => {
    setup({ activities: { "task-1": [buildActivity({ id: "a1" })] } });
    expect((await listTaskActivities(client, "task-1")).map((row) => row.id)).toEqual(["a1"]);
    expect(await listTaskActivities(client, "task-2")).toEqual([]);
  });
});

describe("attachments", () => {
  const png = new File([new Uint8Array(10)], "anh.png", { type: "image/png" });

  it("presigns with the file's name, size and type", async () => {
    const { calls } = setup({});
    const presign = await presignAttachment(client, "task-1", { fileName: "anh.png", fileSize: 10, contentType: "image/png" });
    expect(presign.presigned_url.startsWith(`${STORAGE_ORIGIN}/upload/`)).toBe(true);
    expect(calls[0]).toMatchObject({
      path: "/tasks/task-1/attachments/presigned-url/",
      idempotencyKey: null,
      body: { file_name: "anh.png", file_size: 10, content_type: "image/png" },
    });
  });

  it("sends the file straight to storage with the presigned headers and no auth", async () => {
    let seen: { url: string; init: RequestInit | undefined } | null = null;
    const fetchImpl = ((url: string, init?: RequestInit) => {
      seen = { url, init };
      return Promise.resolve(new Response(null, { status: 200 }));
    }) as unknown as typeof fetch;
    await uploadToStorage({ presigned_url: "https://r2.test/x", headers: { "Content-Type": "image/png" } }, png, fetchImpl);
    expect(seen).toMatchObject({ url: "https://r2.test/x", init: { method: "PUT", headers: { "Content-Type": "image/png" } } });
  });

  it("reports a storage rejection and a network/CORS failure as ApiError", async () => {
    const rejecting = (() => Promise.resolve(new Response(null, { status: 403 }))) as unknown as typeof fetch;
    expect((await failureOf(uploadToStorage({ presigned_url: "u", headers: {} }, png, rejecting))).status).toBe(403);
    const blocked = (() => Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch;
    const error = await failureOf(uploadToStorage({ presigned_url: "u", headers: {} }, png, blocked));
    expect(error.status).toBe(0);
    expect(error.message).toContain("kho lưu trữ");
  });

  it("confirms with an Idempotency-Key and refuses without one", async () => {
    const { calls } = setup({});
    const presign = await presignAttachment(client, "task-1", { fileName: "a.png", fileSize: 10, contentType: "image/png" });
    const confirmed = await confirmAttachment(client, "task-1", { attachmentId: presign.attachment_id, idempotencyKey: "key-1" });
    expect(confirmed.status).toBe("CONFIRMED");
    expect(calls.at(-1)).toMatchObject({ path: "/tasks/task-1/attachments/", idempotencyKey: "key-1", body: { attachment_id: presign.attachment_id } });
    expect((await listTaskAttachments(client, "task-1")).map((row) => row.id)).toEqual([presign.attachment_id]);
  });

  it("runs presign → storage → confirm in order and stops at the first failure", async () => {
    const { calls } = setup({});
    const confirmed = await uploadTaskAttachment(client, "task-1", png);
    expect(confirmed.file_name).toBe("anh.png");
    expect(calls.map((call) => call.method + " " + call.path.replace(/new-\d+$/, "new"))).toEqual([
      "POST /tasks/task-1/attachments/presigned-url/",
      "PUT /storage/upload/attachment-new",
      "POST /tasks/task-1/attachments/",
    ]);
    expect(calls[2].idempotencyKey).toEqual(expect.any(String));

    const rejected = setup({ storageStatus: 403 });
    expect((await failureOf(uploadTaskAttachment(client, "task-1", png))).status).toBe(403);
    expect(rejected.calls.some((call) => call.path === "/tasks/task-1/attachments/")).toBe(false);
  });

  it("maps an expired presign to 422 and an unavailable store to 503", async () => {
    setup({ presignExpired: true });
    expect((await failureOf(uploadTaskAttachment(client, "task-1", png))).status).toBe(422);
    setup({ storageUnavailable: true });
    expect((await failureOf(uploadTaskAttachment(client, "task-1", png))).status).toBe(503);
  });

  it("asks for a fresh download link and removes an attachment", async () => {
    setup({ attachments: [buildAttachment({ id: "att-1" })] });
    expect(await getAttachmentDownloadUrl(client, "task-1", "att-1")).toBe(`${STORAGE_ORIGIN}/download/att-1`);
    expect((await deleteAttachment(client, "task-1", "att-1")).deleted_at).not.toBeNull();
    expect(await listTaskAttachments(client, "task-1")).toEqual([]);
  });
});
