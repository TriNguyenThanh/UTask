import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ensureCsrfToken } from "@/lib/api/csrf";

function clearCookie() {
  document.cookie = "csrftoken=; Max-Age=0; Path=/";
}

beforeEach(clearCookie);
afterEach(() => {
  clearCookie();
  vi.unstubAllGlobals();
});

describe("ensureCsrfToken", () => {
  it("returns the existing cookie without any request", async () => {
    document.cookie = "csrftoken=abc%20123; Path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    expect(await ensureCsrfToken("")).toBe("abc 123");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("warms up through the docs page and reads the cookie it sets", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => {
      document.cookie = "csrftoken=fresh; Path=/";
      return new Response("");
    });
    vi.stubGlobal("fetch", fetchMock);

    expect(await ensureCsrfToken("https://api.test/")).toBe("fresh");
    expect(fetchMock).toHaveBeenCalledWith("https://api.test/api/auth/docs/", { credentials: "include" });
  });

  it("returns null when the backend sets no cookie or is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("")));
    expect(await ensureCsrfToken("")).toBeNull();

    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("down"))));
    expect(await ensureCsrfToken("")).toBeNull();
  });
});
