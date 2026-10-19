import { describe, expect, it } from "vitest";

import { deviceName } from "@/features/auth/deviceName";

describe("deviceName", () => {
  it.each([
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Chrome trên Windows"],
    ["Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36 Edg/120", "Edge trên Windows"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/121.0", "Firefox trên macOS"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Version/17 Safari/604.1", "Safari trên iOS"],
    ["Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36", "Chrome trên Android"],
  ])("parses %s", (userAgent, expected) => {
    expect(deviceName(userAgent)).toBe(expected);
  });

  it("falls back when the user agent is not recognised", () => {
    expect(deviceName("curl/8.0")).toBe("Trình duyệt web");
    expect(deviceName("")).toBe("Trình duyệt web");
  });
});
