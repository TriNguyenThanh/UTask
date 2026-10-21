import { screen, waitFor, within, type BoundFunctions, type queries } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fixture, main, record, setup, type Seen } from "@/features/teacher/realTeacherTestkit";
import {
  buildActivity,
  buildEnrollment,
  buildGroup,
  buildMember,
  envelope,
  envelopeError,
  type ClassroomFixture,
} from "@/test/classroomHandlers";

/**
 * Phase 8 on the teacher side, against the (simulated) real Classroom service:
 * removing a student, adding/importing students, adjusting teams, history.
 */

afterEach(() => vi.unstubAllEnvs());

const PEOPLE = [
  { id: "u1", name: "An", code: "S01" },
  { id: "u2", name: "Bình", code: "S02" },
  { id: "u3", name: "Chi", code: "S03" },
  { id: "u4", name: "Dũng", code: "S04" },
];

function profile(person: (typeof PEOPLE)[number]) {
  return { display_name: person.name, email: `${person.id}@st.edu.vn`, student_id: person.code };
}

/** g1 = An (Leader) + Chi, g2 = Bình (Leader); Dũng has no team. */
function roster(overrides: Partial<ClassroomFixture> = {}): ClassroomFixture {
  const [an, binh, chi, dung] = PEOPLE;
  return fixture({
    enrollments: {
      "class-1": PEOPLE.map((person) => buildEnrollment({ id: `e-${person.id}`, user_id: person.id, profile: profile(person) })),
    },
    groups: {
      "class-1": [buildGroup({ id: "g1", name: "Nhóm 1", source_version: 3 }), buildGroup({ id: "g2", name: "Nhóm 2", source_version: 5 })],
    },
    members: {
      g1: [
        buildMember({ id: "m1", group_id: "g1", user_id: an.id, role: "LEADER", profile: profile(an) }),
        buildMember({ id: "m3", group_id: "g1", user_id: chi.id, role: "MEMBER", profile: profile(chi) }),
      ],
      g2: [buildMember({ id: "m2", group_id: "g2", user_id: binh.id, role: "LEADER", profile: profile(binh) })],
    },
    users: [
      ...(fixture().users ?? []),
      { id: dung.id, email: "u4@st.edu.vn", student_id: dung.code, display_name: dung.name, avatar_url: null, bio: null, roles: ["STUDENT"], account_status: "ACTIVE" },
    ],
    ...overrides,
  });
}

function importResult(students: Array<{ row_number: number; email?: string; student_id?: string }>) {
  return {
    summary: {
      total_records: students.length,
      enrolled: students.length,
      already_enrolled: 0,
      failed: 0,
      created_accounts: 0,
      existing_accounts: students.length,
      flagged: 0,
      duplicates: 0,
    },
    results: students.map((row) => ({
      row_number: row.row_number,
      user_id: `x-${row.row_number}`,
      email: row.email ?? null,
      student_id: row.student_id ?? null,
      account_status: "ACTIVE",
      account_result: "EXISTING",
      reason: null,
      enrollment_id: `en-${row.row_number}`,
      enrollment_result: "ENROLLED",
    })),
  };
}

function rowsOf(seen: Seen) {
  return seen.body.students as Array<{ row_number: number; email?: string; student_id?: string }>;
}

describe("removing a student from the class", () => {
  it("asks for a reason, then sends it with an idempotency key", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/enrollments/e-u2/exit/", () => envelope({ id: "e-u2", status: "REMOVED" }));
    setup("/teacher/courses/class-1/students", roster());
    const user = userEvent.setup();
    const page = await main();
    await user.click((await page.findAllByRole("button", { name: "Loại khỏi lớp Bình" }))[0]);
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Lý do"), "ab");
    await user.click(dialog.getByRole("button", { name: /Loại khỏi lớp/ }));
    expect(seen).toHaveLength(0);

    await user.type(dialog.getByLabelText("Lý do"), "c do nghỉ học");
    await user.click(dialog.getByRole("button", { name: /Loại khỏi lớp/ }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ reason: "abc do nghỉ học" });
    expect(seen[0].key).toBeTruthy();
  });

  it("warns about a Leader and shows the server's refusal when no successor is set", async () => {
    record("post", "/api/classroom/classes/class-1/enrollments/e-u1/exit/", () =>
      envelopeError(409, "LEADER_SUCCESSOR_REQUIRED", "Hãy chọn Leader mới trước khi rời nhóm."),
    );
    setup("/teacher/courses/class-1/students", roster());
    const user = userEvent.setup();
    const page = await main();
    await user.click((await page.findAllByRole("button", { name: "Loại khỏi lớp An" }))[0]);
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/đang là Leader/)).toBeInTheDocument();
    await user.type(dialog.getByLabelText("Lý do"), "Nghỉ học");
    await user.click(dialog.getByRole("button", { name: /Loại khỏi lớp/ }));
    expect(await screen.findByText("Hãy chọn Leader mới trước khi rời nhóm.")).toBeInTheDocument();
  });
});

describe("adding one student", () => {
  it("sends one numbered row and reports the per-row outcome", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/students/", (entry) =>
      envelope(importResult(rowsOf({ ...entry }))),
    );
    setup("/teacher/courses/class-1/students", roster());
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Thêm sinh viên" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Thêm sinh viên vào lớp" }));
    await user.type(dialog.getByLabelText(/Email/), "moi@st.edu.vn");
    await user.click(dialog.getByRole("button", { name: /Thêm vào lớp/ }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ students: [{ row_number: 1, email: "moi@st.edu.vn" }] });
    expect(seen[0].key).toBeTruthy();
    expect(await dialog.findByText("Thêm vào lớp (tài khoản có sẵn)")).toBeInTheDocument();
  });

  it("reuses the idempotency key when the same request is retried after a failure", async () => {
    let calls = 0;
    const seen = record("post", "/api/classroom/classes/class-1/students/", (entry) => {
      calls += 1;
      return calls === 1
        ? envelopeError(503, "SERVICE_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.")
        : envelope(importResult(rowsOf({ ...entry })));
    });
    setup("/teacher/courses/class-1/students", roster());
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Thêm sinh viên" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Thêm sinh viên vào lớp" }));
    await user.type(dialog.getByLabelText(/Email/), "moi@st.edu.vn");
    await user.click(dialog.getByRole("button", { name: /Thêm vào lớp/ }));
    await waitFor(() => expect(seen).toHaveLength(1));
    await user.click(await dialog.findByRole("button", { name: /Thêm vào lớp/ }));
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[1].key).toBe(seen[0].key);
  });

  it("explains a refused row in words", async () => {
    record("post", "/api/classroom/classes/class-1/students/", (entry) => {
      const result = importResult(rowsOf({ ...entry }));
      result.summary = { ...result.summary, enrolled: 0, failed: 1, flagged: 1 };
      result.results[0] = { ...result.results[0], account_result: "FLAGGED", reason: "FLAGGED_ROLE_CONFLICT", enrollment_result: "FAILED" } as never;
      return envelope(result);
    });
    setup("/teacher/courses/class-1/students", roster());
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Thêm sinh viên" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Thêm sinh viên vào lớp" }));
    await user.type(dialog.getByLabelText(/Email/), "gv@utask.test");
    await user.click(dialog.getByRole("button", { name: /Thêm vào lớp/ }));
    expect(await dialog.findByText(/giảng viên/i)).toBeInTheDocument();
  });
});

describe("importing a list", () => {
  function csv(count: number, extra: string[] = []) {
    const lines = ["student_id,email"];
    for (let index = 1; index <= count; index += 1) lines.push(`64510${String(index).padStart(5, "0")},sv${index}@st.edu.vn`);
    return [...lines, ...extra].join("\n");
  }

  async function upload(content: string) {
    const user = userEvent.setup();
    const page = await main();
    await user.upload(await page.findByLabelText(/File danh sách/), new File([content], "ds.csv", { type: "text/csv" }));
    return { user, page };
  }

  it("splits 250 rows into batches of 100/100/50 and merges the results", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/students/", (entry) => envelope(importResult(rowsOf({ ...entry }))));
    setup("/teacher/courses/class-1/students/import", roster());
    const { user, page } = await upload(csv(250));
    await user.click(await page.findByRole("button", { name: "Xác nhận nhập (250 dòng)" }));
    await waitFor(() => expect(seen).toHaveLength(3), { timeout: 5000 });
    expect(seen.map((entry) => rowsOf(entry).length)).toEqual([100, 100, 50]);
    expect(new Set(seen.map((entry) => entry.key)).size).toBe(3);
    expect(rowsOf(seen[2])[0].row_number).toBe(202);
    const summary = await page.findByLabelText("Tóm tắt kết quả");
    expect(within(summary).getByText("Đã thêm vào lớp").nextElementSibling).toHaveTextContent("250");
  });

  it("does not send rows with a format error", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/students/", (entry) => envelope(importResult(rowsOf({ ...entry }))));
    setup("/teacher/courses/class-1/students/import", roster());
    const { user, page } = await upload(csv(2, ["64510000099,khong-phai-email"]));
    await user.click(await page.findByRole("button", { name: "Xác nhận nhập (2 dòng)" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(rowsOf(seen[0])).toHaveLength(2);
  });

  it("stops at a failed batch and retries only the unfinished ones with the same key", async () => {
    let calls = 0;
    const seen = record("post", "/api/classroom/classes/class-1/students/", (entry) => {
      calls += 1;
      return calls === 2 ? envelopeError(503, "SERVICE_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng.") : envelope(importResult(rowsOf({ ...entry })));
    });
    setup("/teacher/courses/class-1/students/import", roster());
    const { user, page } = await upload(csv(150));
    await user.click(await page.findByRole("button", { name: "Xác nhận nhập (150 dòng)" }));
    await waitFor(() => expect(seen).toHaveLength(2));
    await user.click(await page.findByRole("button", { name: /Thử lại/ }));
    await waitFor(() => expect(seen).toHaveLength(3));
    expect(seen[2].key).toBe(seen[1].key);
    expect(seen[2].key).not.toBe(seen[0].key);
    expect(rowsOf(seen[2])[0].row_number).toBe(102);
    const summary = await page.findByLabelText("Tóm tắt kết quả");
    expect(within(summary).getByText("Đã thêm vào lớp").nextElementSibling).toHaveTextContent("150");
  });
});

describe("adjusting teams", () => {
  async function open(data: ClassroomFixture = roster()) {
    setup("/teacher/courses/class-1/teams", data);
    const user = userEvent.setup();
    const page = await main();
    await user.click(await page.findByRole("button", { name: "Điều chỉnh nhóm" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Điều chỉnh nhóm" }));
    return { user, dialog };
  }

  async function pick(dialog: BoundFunctions<typeof queries>, label: string | RegExp, optionName: string | RegExp) {
    const select = await dialog.findByLabelText(label);
    await userEvent.selectOptions(select, within(select).getByRole("option", { name: optionName }));
  }

  it("lists a student with no MSSV by name only", async () => {
    const noCode = roster();
    noCode.enrollments = {
      "class-1": PEOPLE.map((person) =>
        buildEnrollment({ id: `e-${person.id}`, user_id: person.id, profile: { ...profile(person), student_id: null } }),
      ),
    };
    const { dialog } = await open(noCode);
    const select = await dialog.findByLabelText("Sinh viên");
    expect(within(select).getByRole("option", { name: "Chi — Nhóm 1" })).toBeInTheDocument();
  });

  it("moves a member with a reason", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/adjust-member/", () => envelope({ moved: true }));
    const { user, dialog } = await open();
    await pick(dialog, "Sinh viên", /Chi/);
    await pick(dialog, "Nhóm đích", /Nhóm 2/);
    const confirm = dialog.getByRole("button", { name: "Xác nhận thay đổi" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("Lý do"), "Cân bằng sĩ số");
    await user.click(confirm);
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ user_id: "u3", target_group_id: "g2", reason: "Cân bằng sĩ số" });
    expect(seen[0].key).toBeTruthy();
  });

  it("takes a Leader out only once a successor is chosen", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/adjust-member/", () => envelope({ moved: true }));
    const { user, dialog } = await open();
    await pick(dialog, "Sinh viên", /An/);
    await pick(dialog, "Nhóm đích", /Nhóm 2/);
    await user.type(dialog.getByLabelText("Lý do"), "Đổi nhóm");
    expect(await dialog.findByText(/sẽ mất Leader/)).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Xác nhận thay đổi" })).toBeDisabled();

    await pick(dialog, /Leader mới của Nhóm 1/, /Chi/);
    await user.click(dialog.getByRole("button", { name: "Xác nhận thay đổi" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ user_id: "u1", target_group_id: "g2", successor_user_id: "u3", reason: "Đổi nhóm" });
  });

  it("takes a member out of every team with a null target", async () => {
    const seen = record("post", "/api/classroom/classes/class-1/adjust-member/", () => envelope({ moved: true }));
    const { user, dialog } = await open();
    await pick(dialog, "Sinh viên", /Chi/);
    await pick(dialog, "Nhóm đích", /Không thuộc nhóm nào/);
    await user.type(dialog.getByLabelText("Lý do"), "Rút khỏi nhóm");
    await user.click(dialog.getByRole("button", { name: "Xác nhận thay đổi" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toEqual({ user_id: "u3", target_group_id: null, reason: "Rút khỏi nhóm" });
  });

  it("shows the server's refusal inside the dialog", async () => {
    record("post", "/api/classroom/classes/class-1/adjust-member/", () =>
      envelopeError(409, "GROUP_FULL", "Nhóm đích đã đủ thành viên."),
    );
    const { user, dialog } = await open();
    await pick(dialog, "Sinh viên", /Chi/);
    await pick(dialog, "Nhóm đích", /Nhóm 2/);
    await user.type(dialog.getByLabelText("Lý do"), "Cân bằng sĩ số");
    await user.click(dialog.getByRole("button", { name: "Xác nhận thay đổi" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("Nhóm đích đã đủ thành viên.");
  });

  it("designates a new Leader with the team's version", async () => {
    const seen = record("post", "/api/classroom/groups/g1/transfer-leader/", () => envelope({ id: "g1" }));
    const { user, dialog } = await open();
    await user.click(await dialog.findByRole("button", { name: "Chỉ định Leader" }));
    await pick(dialog, "Nhóm", /Nhóm 1/);
    await pick(dialog, /Leader mới/, /Chi/);
    await user.type(dialog.getByLabelText("Lý do"), "Leader cũ bận");
    await user.click(dialog.getByRole("button", { name: "Xác nhận thay đổi" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toMatchObject({ version: 3, user_id: "u3", reason: "Leader cũ bận" });
  });

  it("creates a team for a student who has none, without asking for a reason", async () => {
    const seen = record("post", "/api/classroom/groups/", () => envelope(buildGroup({ id: "g3", name: "Nhóm mới" }), { status: 201 }));
    const { user, dialog } = await open();
    await user.click(await dialog.findByRole("button", { name: "Tạo nhóm mới" }));
    expect(dialog.queryByLabelText("Lý do")).not.toBeInTheDocument();
    await user.type(await dialog.findByLabelText(/Tên nhóm/), "Nhóm mới");
    await pick(dialog, /Leader/, /Dũng/);
    await user.click(dialog.getByRole("button", { name: "Xác nhận thay đổi" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].body).toMatchObject({ class_id: "class-1", name: "Nhóm mới", leader_id: "u4" });
  });
});

describe("history", () => {
  const activities = {
    "class-1": [
      buildActivity({ id: "a2", verb: "enrollment.added", created_at: "2026-09-03T08:00:00Z" }),
      buildActivity({ id: "a1", verb: "class.future-verb", actor_user_id: null }),
    ],
    g1: [buildActivity({ id: "g-a1", verb: "group.leader.transferred", subject_type: "Group", subject_id: "g1" })],
  };

  it("lists the class history with who did what, and keeps an unknown verb visible", async () => {
    setup("/teacher/courses/class-1", roster({ activities }));
    const page = await main();
    expect(await page.findByText("Lịch sử lớp")).toBeInTheDocument();
    expect(await page.findByText("Giảng viên thêm sinh viên vào lớp")).toBeInTheDocument();
    expect(page.getByText("class.future-verb")).toBeInTheDocument();
    expect(page.getByText(/Hệ thống/)).toBeInTheDocument();
    expect(await page.findAllByText(/TS\. Đức/)).not.toHaveLength(0);
  });

  it("shows a team's members and its own history", async () => {
    setup("/teacher/courses/class-1/teams/g1", roster({ activities }));
    const page = await main();
    expect(await page.findByRole("heading", { name: "Nhóm 1" })).toBeInTheDocument();
    expect(page.getByText("Leader")).toBeInTheDocument();
    expect(await page.findByText("Chuyển quyền Leader")).toBeInTheDocument();
  });

  it("says plainly when the team does not exist", async () => {
    setup("/teacher/courses/class-1/teams/nope", roster());
    expect(await (await main()).findByText("Không tìm thấy nhóm")).toBeInTheDocument();
  });

  it("shows the server's error when history cannot be read", async () => {
    setup(
      "/teacher/courses/class-1",
      roster(),
      http.get("/api/classroom/classes/class-1/activities/", () => envelopeError(403, "PERMISSION_DENIED", "Bạn không có quyền xem lịch sử.")),
    );
    expect(await (await main()).findByText(/Bạn không có quyền xem lịch sử\./)).toBeInTheDocument();
  });
});
