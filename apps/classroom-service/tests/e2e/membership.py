"""Group membership actions and project queries shared by E2E scenarios."""


def members(api, accounts, project):
    return api(
        "GET", f"/api/work/projects/{project['id']}/members/", token=accounts.tokens["teacher"]
    )["data"]


def transfer(api, accounts, data, target="member", actor="leader"):
    group = api("GET", data.path, token=accounts.tokens[actor])["data"]
    return api(
        "POST",
        data.path + "transfer-leader/",
        token=accounts.tokens[actor],
        body={
            "version": group["source_version"],
            "user_id": accounts.users[target],
            "reason": "Luân phiên phụ trách",
        },
    )["data"]


def lock(api, accounts, section):
    current = api("GET", section.path, token=accounts.tokens["teacher"])["data"]
    api(
        "POST",
        section.path + "lock-grouping/",
        token=accounts.tokens["teacher"],
        body={"version": current["version"]},
    )


def publish(environment, service="classroom", time_budget=20):
    environment.command(
        service,
        "shell",
        "-c",
        f"from apps.messaging.publisher import drain; drain(time_budget={time_budget})",
    )
