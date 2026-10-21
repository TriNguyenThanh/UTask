import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { ApiClientProvider } from "@/lib/api/ApiClientProvider";
import { createTestQueryClient } from "@/lib/query/client";
import { useNotifications } from "@/lib/query/studentFlowHooks";
import { NotificationBell } from "@/features/notifications/components/NotificationBell";
import { NotificationPreferencesPanel } from "@/features/notifications/components/NotificationPreferencesPanel";
import { server } from "@/mocks/server";
import { studentTestSession } from "@/test/render";
const auth = vi.hoisted(() => ({ user: { id: "first" }, accessToken: "first", handleUnauthorized: vi.fn(), refreshAccessToken: vi.fn() }));
vi.mock("@/features/auth/AuthProvider", async (original) => ({ ...await original<object>(), useAuth: () => auth }));
const item = { id: "n1", category: "task-pr", title: "Được giao công việc", body: "Nội dung", at: "2026-10-22T01:00:00Z", read: false, actionLabel: null, target: null };
function setup() {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}><ApiClientProvider baseUrl="http://localhost"><MemoryRouter>{children}</MemoryRouter></ApiClientProvider></QueryClientProvider>;
  return { wrapper, queryClient };
}
beforeEach(() => {
  vi.stubEnv("VITE_REAL_SERVICES", "notifications");
  auth.user = { ...studentTestSession.user, id: "first" };
  auth.accessToken = "first";
});
describe("live notifications", () => {
  it("uses the total unread count and refreshes after reading one item", async () => {
    let read = false;
    server.use(
      http.get("*/api/notifications/", () => HttpResponse.json({ count: 1, next: null, previous: null, results: [{ ...item, read }] })),
      http.get("*/api/notifications/unread-count", () => HttpResponse.json({ count: read ? 0 : 37 })),
      http.post("*/api/notifications/n1/read", () => { read = true; return new HttpResponse(null, { status: 204 }); }),
    );
    const { wrapper } = setup();
    render(<NotificationBell />, { wrapper });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Thông báo (37 chưa đọc)" }));
    await user.click(await screen.findByRole("button", { name: /Được giao công việc/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Thông báo" })).toBeInTheDocument());
    expect(read).toBe(true);
  });
  it("marks all notifications read through the live endpoint", async () => {
    let count = 4;
    server.use(
      http.get("*/api/notifications/", () => HttpResponse.json({ next: null, results: [{ ...item, read: count === 0 }] })),
      http.get("*/api/notifications/unread-count", () => HttpResponse.json({ count })),
      http.post("*/api/notifications/read-all", () => { count = 0; return HttpResponse.json({ count: 4 }); }),
    );
    const { wrapper } = setup();
    render(<NotificationBell />, { wrapper });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Thông báo (4 chưa đọc)" }));
    await user.click(screen.getByRole("button", { name: "Đánh dấu tất cả đã đọc" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Thông báo" })).toBeInTheDocument());
    expect(count).toBe(0);
  });
  it("shows retry for network failure", async () => {
    server.use(http.get("*/api/notifications/", () => HttpResponse.error()), http.get("*/api/notifications/unread-count", () => HttpResponse.json({ count: 0 })));
    const { wrapper } = setup();
    render(<NotificationBell />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Thông báo" }));
    expect(await screen.findByText("Không thể tải thông báo.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeInTheDocument();
  });
  it("loads subsequent pages using the gateway path", async () => {
    server.use(http.get("*/api/notifications/", ({ request }) => HttpResponse.json(new URL(request.url).search ? { next: null, results: [{ ...item, id: "n2" }] } : { next: "https://internal.invalid/api/notifications/?page=2", results: [item] })));
    const { wrapper } = setup();
    const { result } = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    await act(() => result.current.fetchNextPage());
    expect(result.current.data?.map((notification) => notification.id)).toEqual(["n1", "n2"]);
  });
  it("aborts previous account request and excludes its late result", async () => {
    let release!: () => void;
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    server.use(http.get("*/api/notifications/", async ({ request }) => {
      if (request.headers.get("Authorization") === "Bearer first") {
        await new Promise<void>((resolve) => { release = resolve; });
        return HttpResponse.json({ next: null, results: [item] });
      }
      return HttpResponse.json({ next: null, results: [{ ...item, id: "new" }] });
    }));
    const { wrapper } = setup();
    const { result, rerender } = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(release).toBeTypeOf("function"));
    auth.user = { ...auth.user, id: "second" };
    auth.accessToken = "second";
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.data?.[0].id).toBe("new"));
    const oldSignal = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/notifications/"))?.[1]?.signal;
    expect(oldSignal?.aborted).toBe(true);
    fetchSpy.mockRestore();
    await act(async () => release());
    expect(result.current.data?.[0].id).toBe("new");
  });
  it("polls every 30 seconds only in a visible tab and stops on unmount", async () => {
    vi.useFakeTimers();
    let calls = 0;
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    server.use(http.get("*/api/notifications/", () => { calls += 1; return HttpResponse.json({ next: null, results: [] }); }));
    const { wrapper } = setup();
    const hook = renderHook(() => useNotifications(), { wrapper });
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(100); });
      expect(calls).toBe(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(calls).toBe(2);
      visibility.mockReturnValue("hidden");
      act(() => document.dispatchEvent(new Event("visibilitychange")));
      await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
      expect(calls).toBe(2);
      visibility.mockReturnValue("visible");
      act(() => document.dispatchEvent(new Event("visibilitychange")));
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
      expect(calls).toBeGreaterThan(2);
      hook.unmount();
      const afterUnmount = calls;
      await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
      expect(calls).toBe(afterUnmount);
    } finally {
      visibility.mockRestore();
      vi.useRealTimers();
    }
  });

  it("saves email preferences and preserves the value after failure", async () => {
    const preferences = { assignment: true, deadline: true, mention: true, feedback: true };
    let fail = false;
    server.use(
      http.get("*/api/notifications/preferences", () => HttpResponse.json(preferences)),
      http.patch("*/api/notifications/preferences", async ({ request }) => {
        if (fail) return new HttpResponse(null, { status: 503 });
        Object.assign(preferences, await request.json());
        return HttpResponse.json(preferences);
      }),
    );
    const { wrapper } = setup();
    render(<NotificationPreferencesPanel />, { wrapper });
    const checkbox = await screen.findByRole("checkbox", { name: "Phân công công việc" });
    await userEvent.click(checkbox);
    await waitFor(() => expect(checkbox).not.toBeChecked());
    fail = true;
    await userEvent.click(checkbox);
    await waitFor(() => expect(checkbox).not.toBeDisabled());
    expect(checkbox).not.toBeChecked();
  });
});
