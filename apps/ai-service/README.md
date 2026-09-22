# AI Service

**Status: PARTIAL.** This is the AI-first implementation focus. It owns no Work
or GitHub business data and never mutates another service's database.

## Responsibility and scope

The service exposes typed, suggestion-only AI capabilities: task generation,
task decomposition, priority suggestion, workload analysis and project-risk
analysis. Context is obtained through named tools that read a dataset or call
the Work and Integration HTTP APIs.

## Implemented API

- `GET /healthz`
- `POST /api/v1/ai/workload-analysis`
- `POST /api/v1/ai/project-risk-analysis`
- `POST /api/v1/ai/priority-suggestion`
- `POST /api/v1/ai/generate-tasks` (typed failure until an ADK model runtime is configured)

Workload, priority and risk use explicit, tested contextual rules so their
results are explainable. They are suggestions only. Task generation has a
Pydantic contract and Google ADK dependency, but returns a configuration error
instead of fabricated tasks when no model runtime is supplied.

## Data and contracts

The tool names are `get_project_context`, `get_project_members`,
`get_project_tasks`, `get_current_sprint`, `get_member_workload`, and
`get_github_activity`. Dataset and HTTP providers share the same internal
contract. The HTTP provider uses only owning-service APIs.

## Not implemented

Google ADK runtime/model credential integration, task decomposition prompt,
prompt/version management, user approval UI, Work mutation command handoff,
Kafka consumption/publishing, full evaluation coverage and CI model evaluation
credentials are TODO. No direct database connection to another service will be
added for these items.
