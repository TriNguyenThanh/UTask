def draft(client, project_id, name):
    response = client.post(
        f"/api/v1/projects/{project_id}/sprints/",
        {"name": name, "start_date": "2026-10-01", "end_date": "2026-10-14"},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()["data"]
