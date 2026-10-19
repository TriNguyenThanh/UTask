import { subscribeSession, type SessionEvent } from "@/features/auth/sessionEvents";
import { MOCK_USERS, STUDENT_ID, TEACHER_ID } from "@/mocks/data/database";

/**
 * Khi đăng nhập bằng tài khoản thật, phần dữ liệu còn chạy MSW vẫn cần một persona demo.
 * Access token thật được ánh xạ sang persona theo email (nếu trùng tài khoản mock),
 * nếu không thì theo vai trò: TEACHER → giảng viên demo, còn lại → sinh viên demo.
 */
const personaByToken = new Map<string, string>();

function personaFor(user: NonNullable<SessionEvent>["user"]): string {
  const email = user.email.toLowerCase();
  const byEmail = MOCK_USERS.find((candidate) => candidate.email.toLowerCase() === email);
  if (byEmail) {
    return byEmail.id;
  }
  return user.roles.includes("TEACHER") ? TEACHER_ID : STUDENT_ID;
}

export function lookupPersona(token: string): string | null {
  return personaByToken.get(token) ?? null;
}

export function installPersonaBridge(): () => void {
  return subscribeSession((event) => {
    if (!event) {
      personaByToken.clear();
      return;
    }
    personaByToken.set(event.accessToken, personaFor(event.user));
  });
}
