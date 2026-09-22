from app.schemas.models import ProjectContext, WorkloadAnalysis, WorkloadMember


def analyze_workload(project: ProjectContext) -> WorkloadAnalysis:
    assigned = {member.user_id: 0 for member in project.members}
    for task in project.tasks:
        if task.status == "DONE" or not task.assignee_ids:
            continue
        share = task.story_points / len(task.assignee_ids)
        for user_id in task.assignee_ids:
            assigned[user_id] = assigned.get(user_id, 0) + share
    members = []
    overloaded = []
    for member in project.members:
        points = round(assigned[member.user_id])
        utilization = points / member.weekly_capacity if member.weekly_capacity else float("inf")
        status = "OVERLOADED" if utilization > 1 else "BALANCED"
        if status == "OVERLOADED":
            overloaded.append(member.display_name)
        members.append(
            WorkloadMember(
                user_id=member.user_id,
                assigned_story_points=points,
                weekly_capacity=member.weekly_capacity,
                utilization=round(utilization, 2),
                status=status,
            )
        )
    recommendations = [f"Review assignments for {name}." for name in overloaded]
    return WorkloadAnalysis(
        status="IMBALANCED" if overloaded else "BALANCED",
        members=members,
        recommendations=recommendations,
        explanation="Assigned story points are compared with each member's declared weekly capacity.",
    )
