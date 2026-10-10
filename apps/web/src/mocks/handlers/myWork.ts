import { delay, http, HttpResponse, type HttpHandler } from "msw";

import type { MockScenario } from "@/mocks/scenarios";
import {
  buildEmptyTasksOverview,
  buildGitHubActivity,
  buildGitHubDisconnectedActivity,
  buildGitHubNoProjectsActivity,
  buildLeaderOnlyOverview,
  buildMemberOnlyOverview,
  buildMixedOverview,
  buildNoCoursesOverview,
  buildNoTeamOverview,
  buildOverviewForUser,
  buildOverdueOverview,
  buildPendingOnlyOverview,
} from "@/mocks/data/myWork";
import type { MockDatabase } from "@/mocks/data/database";
import type { MockRepository } from "@/mocks/data/storage";
import type { GitHubActivity, MyWorkOverview } from "@/features/my-work/types";

const MY_WORK_OVERVIEW_PATH = "/api/work/api/v1/my-work/overview";
const MY_WORK_GITHUB_PATH = "/api/work/api/v1/my-work/github";

const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" ? delay(1200) : undefined;
}

function parseTokenUserId(request: Request): string | null {
  const header = request.headers.get("Authorization") ?? "";
  return /^Bearer mock-access:([^:]+):/.exec(header)?.[1] ?? null;
}

function overviewForScenario(scenario: MockScenario, db: MockDatabase, userId: string): MyWorkOverview {
  switch (scenario) {
    case "my-work-no-courses":
      return buildNoCoursesOverview(new Date());
    case "my-work-no-team":
      return buildNoTeamOverview(new Date());
    case "my-work-pending-membership":
      return buildPendingOnlyOverview(new Date());
    case "my-work-member":
      return buildMemberOnlyOverview(new Date());
    case "my-work-leader":
      return buildLeaderOnlyOverview(new Date());
    case "my-work-mixed":
      return buildMixedOverview(new Date());
    case "my-work-empty-tasks":
      return buildEmptyTasksOverview(new Date());
    case "my-work-overdue":
      return buildOverdueOverview(new Date());
    default:
      // Default scenario is bound to the logged-in account.
      return buildOverviewForUser(userId, new Date());
  }
}

/**
 * GitHub activity mirrors the scenario: no team / no courses states show
 * the "not in a project yet" payload so the section's empty states are
 * exercised. `my-work-github-error` simulates an integration outage.
 * Runtime disconnects (POST /me/github/disconnect) take precedence.
 */
function githubForScenario(
  scenario: MockScenario,
  db: MockDatabase,
  userId: string,
): GitHubActivity | null {
  switch (scenario) {
    case "my-work-no-courses":
    case "my-work-no-team":
    case "my-work-pending-membership":
      return buildGitHubNoProjectsActivity();
    case "my-work-github-error":
      return null;
    case "student-github-disconnected":
      return buildGitHubDisconnectedActivity();
    default:
      if (db.githubDisconnectedByUser[userId]) {
        return buildGitHubDisconnectedActivity();
      }
      return buildGitHubActivity(new Date());
  }
}

export function createMyWorkHandlers(
  scenario: MockScenario,
  repository: MockRepository,
): HttpHandler[] {
  const { db } = repository;

  return [
    http.get(MY_WORK_OVERVIEW_PATH, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) {
        return HttpResponse.json(
          { detail: "Phiên đăng nhập đã hết hạn." },
          { status: 401 },
        );
      }
      if (scenario === "server-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      return HttpResponse.json(overviewForScenario(scenario, db, userId));
    }),

    http.get(MY_WORK_GITHUB_PATH, async ({ request }) => {
      await sleepFor(scenario);
      const userId = parseTokenUserId(request);
      if (!userId) {
        return HttpResponse.json(
          { detail: "Phiên đăng nhập đã hết hạn." },
          { status: 401 },
        );
      }
      if (scenario === "server-error" || scenario === "my-work-github-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const activity = githubForScenario(scenario, db, userId);
      if (activity === null) {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      return HttpResponse.json(activity);
    }),
  ];
}