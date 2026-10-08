import type { AuthUser } from "@/features/auth/types";
import type { MockScenario } from "@/mocks/scenarios";

export const LEADER_ID = "00000000-0000-4000-8000-000000000001";
export const MEMBER_ID = "00000000-0000-4000-8000-000000000002";
export const STUDENT_ID = "00000000-0000-4000-8000-000000000003";

export const DEMO_PASSWORD = "demo1234";

export const MOCK_USERS: AuthUser[] = [
  {
    id: LEADER_ID,
    email: "leader@utask.test",
    display_name: "Nguyễn Hoàng Nam",
    global_role: "USER",
    capabilities: ["project:create"],
  },
  {
    id: MEMBER_ID,
    email: "member@utask.test",
    display_name: "Đặng Thảo Linh",
    global_role: "USER",
    capabilities: [],
  },
  {
    id: STUDENT_ID,
    email: "student@utask.test",
    display_name: "Lê Minh Khoa",
    global_role: "USER",
    capabilities: [],
  },
];

export interface MockProfileRecord {
  user_id: string;
  display_name: string;
  email: string;
  student_id: string;
}

const profilesByUser: Record<string, MockProfileRecord> = {
  [LEADER_ID]: {
    user_id: LEADER_ID,
    display_name: "Nguyễn Hoàng Nam",
    email: "leader@utask.test",
    student_id: "21120015",
  },
  [MEMBER_ID]: {
    user_id: MEMBER_ID,
    display_name: "Đặng Thảo Linh",
    email: "member@utask.test",
    student_id: "21020872",
  },
  [STUDENT_ID]: {
    user_id: STUDENT_ID,
    display_name: "Lê Minh Khoa",
    email: "student@utask.test",
    student_id: "21020999",
  },
};

export interface MockDatabase {
  profilesByUser: Record<string, MockProfileRecord>;
  authUsersById: Record<string, AuthUser>;
}

export function createInitialDatabase(_scenario: MockScenario): MockDatabase {
  return {
    profilesByUser,
    authUsersById: Object.fromEntries(MOCK_USERS.map((user) => [user.id, user])),
  };
}