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
  /** Editable profile fields managed by the demo PATCH /me/settings. */
  full_name: string;
  cohort_class: string;
  faculty: string;
  phone: string;
  updated_at: string;
}

function profile(
  user_id: string,
  display_name: string,
  email: string,
  student_id: string,
): MockProfileRecord {
  return {
    user_id,
    display_name,
    email,
    student_id,
    full_name: display_name,
    cohort_class: "K21-CNPM-02",
    faculty: "Khoa Công nghệ Phần mềm • Trường ĐH CNTT",
    phone: "0987 654 321",
    updated_at: new Date().toISOString(),
  };
}

/**
 * Session-owned team created through the demo POST /courses/:id/teams.
 * A freshly created team has a draft topic and no workspace yet, so
 * `project_id` stays null and no fake project is provisioned.
 */
export interface MockCreatedTeam {
  teamId: string;
  courseId: string;
  teamName: string;
  description: string;
  neededSkills: string[];
  maxMembers: number;
  /** Creator becomes the leader and the only member until others join. */
  members: { userId: string; role: "leader" | "member"; joinedAt: string }[];
  createdAt: string;
}

export interface MockDatabase {
  profilesByUser: Record<string, MockProfileRecord>;
  authUsersById: Record<string, AuthUser>;
  /** Teams created at runtime, keyed by `${userId}:${courseId}`. */
  createdTeams: Record<string, MockCreatedTeam>;
  /** Per-user notification ids marked read: userId → Set of ids. */
  notificationReadByUser: Record<string, string[]>;
  /** Per-user GitHub disconnect flag (demo session state). */
  githubDisconnectedByUser: Record<string, boolean>;
  /**
   * Per-project AI configuration. Demo stores only provider + metadata —
   * the raw API key is deliberately never persisted here.
   */
  aiConfigByProject: Record<
    string,
    { provider: string; keyConfigured: boolean; keyHint: string; configuredAt: string }
  >;
}

export function createInitialDatabase(_scenario: MockScenario): MockDatabase {
  return {
    profilesByUser: {
      [LEADER_ID]: profile(LEADER_ID, "Nguyễn Hoàng Nam", "leader@utask.test", "21120015"),
      [MEMBER_ID]: profile(MEMBER_ID, "Đặng Thảo Linh", "member@utask.test", "21020872"),
      [STUDENT_ID]: profile(STUDENT_ID, "Lê Minh Khoa", "student@utask.test", "21020999"),
    },
    authUsersById: Object.fromEntries(MOCK_USERS.map((user) => [user.id, user])),
    createdTeams: {},
    notificationReadByUser: {},
    githubDisconnectedByUser: {},
    aiConfigByProject: {},
  };
}