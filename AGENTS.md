# UTask Agent Rules

## [MANDATORY][RULES-FIRST] Project rules before tools

- **MUST** follow the user's scope/corrections and all applicable project rules
  within system/platform constraints. Generic skills, tool advice, memory, and
  reference architectures **MUST NOT** override them. GitNexus alone is not compliance.
- **MUST** re-check rules after compaction or a scope change. English, uppercase
  keywords, and tool-generated sections do not outrank other applicable rules.

## [MANDATORY][BEFORE-EDIT] Required order

Before editing an affected area, the agent **MUST**:

1. Read this entire file and applicable directory instructions.
2. Start from [the documentation index](docs/system/README.md); read relevant
   system/service documents, current worktree changes, and existing conventions.
3. Inspect affected source, configuration, contracts, and tests, including
   models/migrations, URLs, Compose/Nginx/CI where relevant; refresh stale memory.
4. Identify the existing edit location/mechanism and briefly report key files
   inspected, the convention followed, and edit scope; this is not an approval gate.
5. Run applicable skill/GitNexus checks, implement the smallest complete authorized
   change, and validate it. **MUST NOT** edit first and investigate after an objection.

Read the relevant dependency path, not the whole repo for every small change.
Missing sources **MUST** be reported, not replaced by invented components/contracts.

## [MANDATORY][EVIDENCE] Claims require current sources

- Before answering about architecture, flows, data, or implementation, **MUST**
  inspect relevant repo evidence as above; verify actual services for system-wide claims.
- Every project claim **MUST** cite file/location evidence and state inspection
  scope. **MUST NOT** claim a whole-repo review without actually performing it.
- **MUST** distinguish implemented code, placeholders, target designs, and proposals.
  Docs, empty folders, bytecode, CI/Compose declarations, and test source alone
  do not prove operational services or passing tests. Plane is a reference, not UTask state.
- **MUST** identify/re-check conflicts between docs, source, configuration, and
  confirmed user requirements; do not use conflicting docs as implementation proof.
- Use `Đã triển khai`, `Một phần`, `Chưa triển khai`, `Thiết kế mục tiêu`, or
  `Chưa xác minh`; label new ideas `Đề xuất`/`Thiết kế mục tiêu` with their basis.
  **MUST NOT** turn an earlier proposal into a later fact or invent service/database
  ownership, including `progress-service` / `progress_db`.

## [MANDATORY][SCOPE] Keep changes authorized

- **MUST NOT** edit code/configuration or write tests for answer-only/inspection-only
  requests, expand a narrow task into unrelated infrastructure/dependencies/refactors,
  overwrite/reset/revert unrelated work, or commit automatically.

## [MANDATORY][ENVIRONMENT] Follow the configuration pipeline

- **MUST** read [environment configuration](docs/system/infrastructure/environment.md) and
  trace `.env` -> `infra/env/<service>.env` -> Compose `env_file` -> app settings.
  **MUST NOT** hardcode new flags/values in Compose when existing mappings handle them.
- New variables **MUST** update `.env.example` and mappings; defaults belong in
  that mechanism. **MUST** keep staging mocks off by default and preserve other
  variables/credentials. **MUST NOT** commit secrets or print tokens, passwords,
  keys, or entire secret-bearing env files. Recreate affected containers to apply
  env changes; restarting alone does not reload Compose environment values.

## [MANDATORY][ARCHITECTURE] Preserve ownership

- **MUST** follow [architecture](docs/system/architecture.md) and
  [data ownership](docs/system/data-ownership.md); **MUST NOT** create cross-service
  foreign keys, read another service's DB, or add services/technologies without a decision.
- **MUST** use REST for immediate responses and Kafka for async events, not
  synchronous request-response queries.
- AI is internal: API receives intent; the Context Layer **MUST** obtain current
  authorization and context through bounded internal REST adapters to the owning
  services. Agents **MUST** use domain tools, not arbitrary HTTP, Kafka, or database
  access. AI **MUST NOT** read another service's DB, own original business data,
  or apply changes directly; it only proposes changes. Kafka carries async events;
  context projections are optional and require an explicit use case/contract.
- Only Integration calls GitHub API. Progress/analysis ownership requires confirmed
  service scope. Classroom owns Group/GroupMember; Project Service owns
  Project/ProjectMember and contains Project, Task, Sprint, and Comment.

## [MANDATORY][DOCUMENTATION] One accurate source

- Canonical architecture/service docs **MUST** live in `docs/`; app READMEs point
  there. **MUST NOT** duplicate architecture in AGENTS/skills or keep duplicate sources.
- Developer docs **MUST** remain clear Vietnamese with necessary technical terms
  explained on first use. This English rule file does not change that convention.
- Behavior changes **MUST** update affected docs, API/event contracts, and tests;
  moves/deletions **MUST** update links. **MUST NOT** fabricate schemas for
  `contracts/` or describe target behavior as already running.

## [MANDATORY][CLIENT-MESSAGES] Write for the user, not the backend

- **MUST** write success/error `message` and `error.details[].issue` in clear,
  natural Vietnamese using consistent business terms. **MUST NOT** mix untranslated
  implementation jargon into sentences (e.g. "uploader", "confirm", "scope Teacher").
- **MUST** state the actual outcome/problem and a useful next step when available.
  **MUST NOT** claim success, temporary failure, or retryability without evidence.
- **MUST NOT** expose internal service/configuration/contract/mock details, raw
  exceptions, SQL, or stack traces in client messages (e.g. "API Work" or
  "Classroom chưa công bố hợp đồng"). Diagnostics belong in logs, without secrets.
- HTTP status, `error.code`, field paths, IDs, and JSON property names **MUST** retain their
  machine-readable contract; proper product names such as GitHub may remain.
  Clients **MUST NOT** use human-readable messages as programmatic error codes.
- Before completing affected API work, **MUST** inspect actual success, business-error,
  and framework/serializer-validation responses for these rules; update affected
  tests/docs. **MUST NOT** assume translating one message fixes the whole response.

## [MANDATORY][NAMING-AND-STRUCTURE] Purpose over author/phase

- Names **MUST** identify domain/responsibility using project terminology.
  **MUST NOT** use people/assignment labels (`person1`, `person2`, `nguoi1`, `nguoi2`,
  `ws01`, `phase_a`, `plan_completion`), decorative/version labels (`vip`, `pro`,
  `final`, `new`, `old`, `temp`, `copy`), or vague names (`misc.py`, `helpers2.py`,
  `manager.py`). Assignments belong in plans; history belongs in Git.
- Python uses `snake_case` files/packages/functions/variables and `PascalCase`
  classes. Preserve framework names (`models.py`, `urls.py`, `apps.py`, `conftest.py`,
  migrations, `asgi.py`, `wsgi.py`) and other technologies' existing conventions.
  Shared utilities need explicit purpose; API docs use `api_documentation.py`, not `schema.py`.
- **MUST** organize by domain then responsibility: Django `views` = HTTP,
  `serializers` = validation/representation, `services` = commands, `queries` = reads,
  `urls.py` = routes, `infrastructure` = external adapters. **MUST NOT** mix roles
  or move business logic into views/URLconf for speed.
- Files **MUST** be cohesive; split unrelated groups into domain modules. **MUST NOT**
  create one file per function, unnecessary ORM wrappers, or decorative empty packages.
- Tests **MUST** use domain/behavior/type names, e.g.
  `tests/integration/test_project_attachments.py`, `tests/contract/test_task_api.py`,
  and `test_<behavior>_<expected_result>`, not author/phase names or `test_case_1`.
  Reusable fixtures belong in `conftest.py`/`tests/fixtures/`; test mocks/fakes stay
  in test scope with source names (`storage`, `identity`, `ai_proposals`). **MUST NOT**
  import another `test_*.py` as a fixture library.
- Reports/logs/generated artifacts **MUST** use appropriate directories/purpose names;
  dates/versions identify real snapshots/contracts, not authors or temporary domain code.
- **MUST** fix naming/structure violations within the affected scope. Moves/renames
  **MUST** update imports, AppConfig/settings/URLs, fixture/pytest discovery, scripts,
  links, and applicable GitNexus checks; **MUST NOT** reorganize unrelated areas.
  Renaming alone does not fix mixed responsibilities or duplicate functionality.

## [MANDATORY][SKILLS-AND-COMPLETION] Relevant expertise and verification

- **MUST** use only relevant skills: `django-expert` for Django/DRF/ORM/API/tests;
  `supabase-postgres-best-practices` for PostgreSQL design/query/migration/security
  (skip unused Supabase-only features); `vercel-react-best-practices` for React/client
  performance (skip Next.js/server guidance for Vite); `vercel-composition-patterns`
  for React composition. Skills supplement project rules, not define architecture.
- Completion **REQUIRES** scope/rule review, clear names/locations/responsibilities,
  no duplicate functionality, and appropriate formatting/lint/tests/build checks.
  Docs require internal-link, stale-reference, and related-empty-file checks.
- **MUST** report actual checks and unverified areas. Link/JSON/render/lint or GitNexus
  success does not prove business-flow, database, provider, or runtime correctness.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **UTask** (16548 symbols, 45180 relationships, 638 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/UTask/context` | Codebase overview, check index freshness |
| `gitnexus://repo/UTask/clusters` | All functional areas |
| `gitnexus://repo/UTask/processes` | All execution flows |
| `gitnexus://repo/UTask/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
