import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { assigneeLabel, capacityUsagePercent, DashboardBody } from "@/features/projects/components/ProjectDashboard";
import { buildDashboard, buildProjectMember } from "@/test/workHandlers";

describe("capacityUsagePercent", () => {
  it("divides allocated points by weekly capacity and rounds", () => {
    expect(capacityUsagePercent(10, 40)).toBe(25);
    expect(capacityUsagePercent(2, 3)).toBe(67);
    expect(capacityUsagePercent(60, 40)).toBe(150);
  });

  it("returns null when there is nothing to divide by", () => {
    expect(capacityUsagePercent(5, null)).toBeNull();
    expect(capacityUsagePercent(5, 0)).toBeNull();
  });
});

describe("assigneeLabel", () => {
  const members = [
    buildProjectMember({ user_id: "u1", display_name: "Đặng Thảo Linh" }),
    buildProjectMember({ id: "pm-2", user_id: "u2", display_name: "" }),
  ];

  it("uses the member's name", () => {
    expect(assigneeLabel("u1", members)).toBe("Đặng Thảo Linh");
  });

  it("falls back to a short id for an unknown member or an empty name", () => {
    expect(assigneeLabel("u2", members)).toBe("Thành viên u2");
    expect(assigneeLabel("abcdef123456", members)).toBe("Thành viên abcdef");
  });
});

describe("DashboardBody capacity column", () => {
  it("shows the estimated usage per person and a dash without capacity", () => {
    const dashboard = buildDashboard({
      assignee_distribution: [
        { user_id: "u1", status: "ACTIVE", weekly_capacity: 20, assigned_work_item_count: 3, unestimated_work_item_count: 0, allocated_estimate_points: 5 },
        { user_id: "u2", status: "ACTIVE", weekly_capacity: null, assigned_work_item_count: 1, unestimated_work_item_count: 1, allocated_estimate_points: 2 },
      ],
    });
    render(<DashboardBody dashboard={dashboard} members={[buildProjectMember({ user_id: "u1", display_name: "Linh" })]} />);
    expect(screen.getByRole("columnheader", { name: "Dùng capacity (ước lượng)" })).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("25%")).toBeInTheDocument();
    expect(within(rows[1]).getAllByText("—").length).toBeGreaterThan(0);
  });
});
