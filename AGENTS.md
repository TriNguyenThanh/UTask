# UTask Agent Rules

- Treat `docs/architecture/UTask_Architecture_Technology_Baseline.md` as the source of truth.
- Preserve the defined architecture and service boundaries; do not introduce unapproved services or technologies.
- Inspect and reuse existing code, components, and contracts before creating new ones; avoid duplication.
- Never fake an implementation or claim incomplete functionality is working.
- Update affected contracts, tests, and README files when behavior changes.
- Run the relevant formatter, lint, tests, and build before reporting completion.

## Skill Use

- Use no skill when none is needed. Otherwise, use the single most relevant skill; use at most two only for genuinely cross-domain work. Never load all skills at once.
- `django-expert`: Django, DRF, ORM, models, serializers, permissions, and migrations.
- `supabase-postgres-best-practices`: PostgreSQL schemas, indexes, queries, and performance.
- `vercel-react-best-practices`: React performance, rendering, and data fetching.
- `vercel-composition-patterns`: Component reuse, composition, and duplicate UI prevention.
