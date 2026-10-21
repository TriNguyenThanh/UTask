import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type HttpHandler } from "msw";
import { describe, expect, it, vi } from "vitest";

import { buildPatch, formFromUser, IdentityProfilePage } from "@/features/notifications/components/IdentityProfilePage";
import { buildMockAuthUser } from "@/mocks/data/authUsers";
import { createMemoryRepository } from "@/mocks/data/storage";
import { createAuthHandlers } from "@/mocks/handlers/auth";
import { server } from "@/mocks/server";
import { leaderTestSession, renderApp } from "@/test/render";

/** Handler auth mock bị bỏ khi `auth` là service thật, nên cài lại tại đây; `overrides` được ưu tiên. */
function setup(...overrides: HttpHandler[]) {
  vi.stubEnv("VITE_REAL_SERVICES", "auth");
  server.use(...overrides, ...createAuthHandlers("default", createMemoryRepository("default")));
  return renderApp(<IdentityProfilePage />, { route: "/settings/profile", session: leaderTestSession });
}

describe("IdentityProfilePage", () => {
  it("keeps email and username read-only while allowing MSSV edits", async () => {
    setup();

    expect(await screen.findByLabelText("Email")).toHaveValue("leader@utask.test");
    expect(screen.getByLabelText("Email")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Tên đăng nhập")).toHaveAttribute("readonly");
    expect(screen.getByLabelText(/Mã số sinh viên/)).not.toHaveAttribute("readonly");
    expect(screen.getByLabelText("Múi giờ")).toHaveValue("Asia/Ho_Chi_Minh");
    expect(screen.getByRole("button", { name: /Lưu thông tin hồ sơ/ })).toBeDisabled();
  });

  it("sends only the changed fields, then shows the server's saved profile", async () => {
    let body: unknown;
    const user = userEvent.setup();
    setup(
      http.patch("/api/auth/users/me", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ success: true, message: "OK", data: {}, meta: null, error: null });
      }),
    );

    const phone = await screen.findByLabelText("Số điện thoại");
    const studentId = screen.getByLabelText(/Mã số sinh viên/);
    await user.type(phone, "0901234567");
    await user.type(studentId, " sv-001 ");
    await user.click(screen.getByRole("button", { name: /Lưu thông tin hồ sơ/ }));

    expect(await screen.findByText("Đã lưu thông tin hồ sơ")).toBeInTheDocument();
    expect(body).toEqual({ phone_number: "0901234567", student_id: "SV-001" });
  });

  it("keeps the saved value after a refetch (persisted by the server)", async () => {
    const user = userEvent.setup();
    const authHandlers = createAuthHandlers("default", createMemoryRepository("default"));
    const view = setup(...authHandlers);

    await user.type(await screen.findByLabelText("Khóa"), "K64");
    await user.click(screen.getByRole("button", { name: /Lưu thông tin hồ sơ/ }));
    await screen.findByText("Đã lưu thông tin hồ sơ");
    view.unmount();

    setup(...authHandlers);
    expect(await screen.findByLabelText("Khóa")).toHaveValue("K64");
  });

  it("shows VALIDATION_ERROR under the offending field", async () => {
    const user = userEvent.setup();
    setup(
      http.patch("/api/auth/users/me", () =>
        HttpResponse.json(
          {
            success: false,
            message: "Dữ liệu đầu vào không hợp lệ.",
            data: null,
            error: { code: "VALIDATION_ERROR", details: [{ field: "phone_number", issue: "Enter a valid phone number." }] },
          },
          { status: 400 },
        )),
    );

    await user.type(await screen.findByLabelText("Số điện thoại"), "abc");
    await user.click(screen.getByRole("button", { name: /Lưu thông tin hồ sơ/ }));

    expect(await screen.findByText("Enter a valid phone number.")).toBeInTheDocument();
  });

  it("reports a failure without field errors as a toast and keeps the edit", async () => {
    const user = userEvent.setup();
    setup(http.patch("/api/auth/users/me", () => HttpResponse.error()));

    await user.type(await screen.findByLabelText("Số điện thoại"), "0901");
    await user.click(screen.getByRole("button", { name: /Lưu thông tin hồ sơ/ }));

    expect(await screen.findByText("Không thể kết nối đến máy chủ.")).toBeInTheDocument();
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0901");
  });

  it("discards edits with Hủy thay đổi", async () => {
    const user = userEvent.setup();
    setup();

    const phone = await screen.findByLabelText("Số điện thoại");
    await user.type(phone, "0901");
    await user.click(screen.getByRole("button", { name: "Hủy thay đổi" }));

    await waitFor(() => expect(phone).toHaveValue(""));
  });

  it("shows an error state when the profile cannot be loaded", async () => {
    setup(http.get("/api/auth/users/me", () => HttpResponse.json({}, { status: 500 })));

    expect(await screen.findByRole("button", { name: /Thử lại/ })).toBeInTheDocument();
  });
});

describe("buildPatch", () => {
  const user = buildMockAuthUser({ id: "u", email: "u@x.vn", display_name: "A B", roles: ["STUDENT"] });

  it("is empty when nothing changed", () => {
    expect(buildPatch(user, formFromUser(user))).toEqual({});
  });

  it("trims text and normalizes MSSV before sending only changed fields", () => {
    expect(buildPatch(user, {
      ...formFromUser(user),
      first_name: "  Bình  ",
      bio: "   ",
      student_id: "  sv-001 ",
    })).toEqual({ first_name: "Bình", student_id: "SV-001" });
  });

  it("clears an optional field with null but never a required one", () => {
    const filled = { ...user, phone_number: "0901", first_name: "A", student_id: "SV-001" };
    expect(buildPatch(filled, {
      ...formFromUser(filled),
      phone_number: "",
      first_name: "",
      student_id: "",
    })).toEqual({
      phone_number: null,
      first_name: "",
      student_id: null,
    });
  });
});
