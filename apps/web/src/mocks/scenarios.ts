export const MOCK_SCENARIOS = [
  "default",
  "slow-network",
  "server-error",
  "my-work-no-courses",
  "my-work-no-team",
  "my-work-pending-membership",
  "my-work-member",
  "my-work-leader",
  "my-work-mixed",
  "my-work-empty-tasks",
  "my-work-overdue",
  "my-work-github-error",
  "student-no-courses",
  "student-no-team",
  "student-join-pending",
  "student-team-leader-topic-draft",
  "student-team-member-topic-pending",
  "student-topic-revision-required",
  "student-project-member",
  "student-project-leader",
  "student-mixed-memberships",
  "student-github-disconnected",
  "student-ai-key-missing",
  "student-empty",
  "student-loading",
  "student-partial-error",
  "student-forbidden",
] as const;

export type MockScenario = (typeof MOCK_SCENARIOS)[number];

export function resolveMockScenario(value: string | undefined): MockScenario {
  const scenario = value || "default";
  if (MOCK_SCENARIOS.some((candidate) => candidate === scenario)) {
    return scenario as MockScenario;
  }
  throw new Error(
    `Unknown VITE_MOCK_SCENARIO "${scenario}". Expected one of: ${MOCK_SCENARIOS.join(", ")}.`,
  );
}