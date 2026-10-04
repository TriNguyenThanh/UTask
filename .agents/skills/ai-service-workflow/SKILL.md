---
name: ai-service-workflow
description: Implement or review UTask AI Service bounded-agent workflows, Context Tool Pool tools, structured proposals, and phase-1 intent behavior.
---

# UTask AI Service Workflow

Use this skill when changing or reviewing UTask AI Service code, tests, API,
workflow orchestration, agent tools, provider adapters, or context access.

Apply progressive disclosure. First read:

- `docs/ai-service/README.md` — task-to-document router;
- `apps/ai-service/AGENTS.md` — repository rules and validation requirements.

Then read only the documents and sections selected by
`references/document-routing.md`. Do not load all AI Service documents by
default. For example, an API-only task normally needs `docs/ai-service/api.md`
and the relevant boundary/request section of `architecture.md`; it does not
need the full `workflow.md` or `erd.md`.

## Phase-1 boundary

Only these intents are in scope:

- `backlog_generation`;
- `task_decomposition`;
- `risk_analysis`.

Other intents are phase 2 unless the user explicitly changes the scope.

## Required architecture

When the task touches agent runtime, read the relevant sections of
`docs/ai-service/workflow.md` before editing. When it touches persistence or
context projection, read `docs/ai-service/erd.md`; when it touches transport or
response schema, read `docs/ai-service/api.md`. Use `code-map.md` only to locate
implementation or verify current entry points.

Keep the dependency direction:

```text
API transport → application → ADK Workflow → LlmAgent → Context Tool Pool
                                                     → Context Layer/adapters
```

- The ADK Workflow owns the macro-flow: request validation, agent execution,
  output validation, bounded revise/retry, and result persistence.
- `LlmAgent` owns bounded reasoning and chooses which domain context tools to
  call. Do not hard-code every possible context fetch into the workflow.
- Tools must be domain-level (`get_task_context`, `get_project_context`,
  `get_team_context`, `get_progress_context`, or
  `get_development_context`). Do not expose Kafka, database, cache, offset,
  replay, or consumer-group operations to the agent.
- Context Layer and deterministic SQL/Python code filter and aggregate data
  before the agent sees it. The agent must not call another service's REST API
  or database.
- Kafka consumers update local context projections outside the agent loop.

## Proposal and safety rules

- AI returns structured proposals; it never directly changes Project, Task,
  Sprint, member, GitHub, or progress data.
- Domain services perform authorization, business validation, and applying a
  user-confirmed proposal.
- Validate every backend-facing output against a typed schema. Invalid output
  may be revised/retried only within explicit limits.
- Give each workflow/agent limits for model calls, context-tool calls,
  specialist calls, output tokens, and wall-clock time. No unbounded loops.
- Use specialist agents only for a real subproblem and prefer agent-as-tool.
- Keep model/provider selection behind an adapter or router; do not couple
  business logic to one provider.

## Testing and task tracking

- Use deterministic fake providers and context-tool doubles in unit tests.
- Cover success and meaningful failure/edge paths, including missing/stale
  context, invalid structured output, tool failure, timeout, and authorization
  boundary where relevant.
- After every prompt that changes code under `apps/ai-service/**`, update
  `apps/ai-service/.agent/TASKS.md` in the same change with completed work,
  files, tests/checks, and remaining/next tasks.
