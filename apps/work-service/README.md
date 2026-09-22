# Work Service

**Status: PARTIAL.** This is the core owner of project workflow data. It owns
projects, logical project members, sprints, tasks, task assignments and their
AI-relevant fields (status, priority, story points and deadline).

## Scope and ownership

`Project`, `ProjectMember`, `Sprint`, `Task`, and `TaskAssignment` are persisted
in this service database. A member's `user_id` is a logical Identity reference;
there is no cross-service foreign key.

## Implemented API

- `GET, POST /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `GET /api/v1/projects/{id}/members`
- `GET, POST /api/v1/projects/{id}/tasks`
- `GET /api/v1/projects/{id}/sprints`
- `PATCH /api/v1/tasks/{id}`
- `GET /healthz`

These APIs are the approved read/write boundary for AI context and subsequent
user-approved AI actions.

## Not implemented

Backlog, epic, user story, comments, labels, workflow configuration, activity
history, progress aggregation, authorization/JWT validation, outbox/Celery and
Kafka publishing remain TODO. No event is published yet.
