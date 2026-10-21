import { lookupPersona } from "@/mocks/personaBridge";

const MOCK_TOKEN_PATTERN = /^mock-access:([^:]+):/;

/**
 * Xác định persona MSW từ header `Authorization`: token mock (`mock-access:<id>:…`)
 * hoặc access token thật đã đăng ký qua cầu nối persona.
 */
export function resolveMockUserId(request: Request): string | null {
  const header = request.headers.get("Authorization") ?? "";
  const token = /^Bearer (.+)$/.exec(header)?.[1];
  if (!token) {
    return null;
  }
  return MOCK_TOKEN_PATTERN.exec(token)?.[1] ?? lookupPersona(token);
}
