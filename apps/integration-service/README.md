# Integration Service

**Status: PARTIAL.** This service owns normalized GitHub data for UTask and is the only boundary through which AI obtains GitHub activity.

## Scope and owned data

The current schema owns repository metadata, commits, pull requests and a logical task-to-GitHub-reference mapping. `project_id` and `task_id` are logical Work Service references, never cross-database foreign keys.

## Implemented API

- `GET, POST /api/v1/integrations/github/repositories`
- `POST /api/v1/integrations/github/repositories/{id}/commits`
- `POST /api/v1/integrations/github/repositories/{id}/pull-requests`
- `GET /api/v1/projects/{project_id}/github-activity`
- `GET /healthz`

## Not implemented

GitHub App installation/authentication, REST client synchronization, webhook signature verification, idempotency, retries, issue/branch ingestion, Kafka events and contribution projections are TODO. API writes are development boundary tests, not a GitHub sync.
