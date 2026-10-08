import { delay, http, HttpResponse, type HttpHandler } from "msw";

import type { MockScenario } from "@/mocks/scenarios";
import {
  buildEmptyTasksOverview,
  buildGitHubActivity,
  buildLeaderOnlyOverview,
  buildMemberOnlyOverview,
  buildMixedOverview,
  buildNoCoursesOverview,
  buildNoTeamOverview,
  buildOverdueOverview,
  buildPendingOnlyOverview,
} from "@/mocks/data/myWork";
import type { GitHubActivity, MyWorkOverview } from "@/features/my-work/types";

const MY_WORK_OVERVIEW_PATH = "/api/work/api/v1/my-work/overview";
const MY_WORK_GITHUB_PATH = "/api/work/api/v1/my-work/github";

const SERVER_ERROR = "Lỗi hệ thống, vui lòng thử lại sau.";

function sleepFor(scenario: MockScenario): Promise<void> | undefined {
  return scenario === "slow-network" ? delay(1200) : undefined;
}

function overviewForScenario(scenario: MockScenario): MyWorkOverview {
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
      return buildMixedOverview(new Date());
  }
}

/**
 * GitHub activity mirrors the scenario: no team / no courses states show
 * the "not in a project yet" payload so the section's empty states are
 * exercised. `my-work-github-error` simulates an integration outage.
 */
function githubForScenario(scenario: MockScenario): GitHubActivity | null {
  switch (scenario) {
    case "my-work-no-courses":
    case "my-work-no-team":
    case "my-work-pending-membership":
      return {
        sync: { state: "connected", linkedProjectCount: 0 },
        pullRequests: [],
        commits: [],
      };
    case "my-work-github-error":
      return null;
    default:
      return buildGitHubActivity(new Date());
  }
}

export function createMyWorkHandlers(scenario: MockScenario): HttpHandler[] {
  return [
    http.get(MY_WORK_OVERVIEW_PATH, async () => {
      await sleepFor(scenario);
      if (scenario === "server-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      return HttpResponse.json(overviewForScenario(scenario));
    }),

    http.get(MY_WORK_GITHUB_PATH, async () => {
      await sleepFor(scenario);
      if (scenario === "server-error" || scenario === "my-work-github-error") {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      const activity = githubForScenario(scenario);
      if (activity === null) {
        return HttpResponse.json({ detail: SERVER_ERROR }, { status: 500 });
      }
      return HttpResponse.json(activity);
    }),
  ];
}