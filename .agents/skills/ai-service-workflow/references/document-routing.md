# AI Service document routing

Use this reference to select the smallest useful document set. It is a routing
table, not a requirement to read every linked file.

## Selection order

1. Read `docs/ai-service/README.md`.
2. Classify the task using the table below.
3. Read the mandatory document(s) and only the named sections.
4. Add optional documents only when the change crosses that boundary.
5. If the task is documentation-only, read the target file and direct links
   needed to check consistency; do not load unrelated implementation design.

## Task routing

| Task keywords | Mandatory | Optional |
| --- | --- | --- |
| API, endpoint, request, response, OpenAPI, contract | `api.md`; `architecture.md`: boundary, Request semantics | `workflow.md`: Workflow/LlmAgent and Structured Output; `erd.md`: AI_REQUEST if persistence changes |
| workflow, agent, tool, prompt, autonomy, specialist | `workflow.md`: Workflow/LlmAgent, Context Tool Pool, Bounded Autonomy, Proposal, Agent Budget | `api.md`: response schema; `architecture.md`: Dependency direction/Failure isolation; `erd.md`: execution persistence |
| context, Kafka, event, consumer, read model, stale | `architecture.md`: Context flow; `workflow.md`: Context Tool Pool and Kafka; `erd.md`: ERD MVP/context tables | `api.md`: Context and response metadata; `code-map.md`: implementation locations |
| database, projection, migration, index, retention | `erd.md`: ERD MVP, constraints/indexes, expansion decisions; `architecture.md`: Context flow | `api.md`: fields exposed externally; `workflow.md`: tool/context behavior |
| provider, model, retry, timeout, budget, structured output | `workflow.md`: Agent Budget, Structured Output, Model Strategy; `architecture.md`: Failure isolation | `api.md`: output/error contract |
| code location, entry point, implementation audit | `code-map.md`: matching section | The design document for the audited component |
| stack, dependency, framework | `tech-stack.md` | `workflow.md`: Framework/Model Strategy only if the decision affects runtime design |

## Section lookup

Use headings instead of reading a long file from the beginning:

- `workflow.md`: `## 3` for workflow/agent, `## 4` for context tools, `## 5`
  for Kafka, `## 6–7` for autonomy/proposal, `## 9–10` for budget/output,
  `## 11–13` for framework/model/cost.
- `architecture.md`: `Request semantics` for API input, `Context flow` for
  events/read model, `Dependency direction` for layers, `Failure isolation`
  for errors and availability.
- `erd.md`: `ERD MVP` for entities, `Ràng buộc và index tối thiểu` for
  persistence constraints, `Quyết định cần chốt` for open decisions.
- `api.md`: sections `4–7` for endpoint contract, `8` for context correctness,
  `9` for proposal application boundary, `11` for unresolved contract choices.

If headings or numbering change, search by heading name rather than relying on
these section numbers.

## Avoid unnecessary context

- Do not read `workflow.md` in full for a request/response documentation edit.
- Do not read `erd.md` for a prompt-only or provider-only change.
- Do not read `tech-stack.md` to implement behavior already defined by API or
  workflow documents.
- Do not read `code-map.md` unless locating or auditing implementation.
- Do not infer implementation status from any design document; use the status
  labels and source evidence required by `AGENTS.md`.

