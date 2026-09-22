# UTask coding rules

1. Read `docs/architecture/UTask_Architecture_Technology_Baseline.md` before changing architecture or a service.
2. Preserve the defined coarse-grained boundaries; do not add services or technology outside the baseline.
3. Each service owns its database. Cross-service reads use an API, events, or a local projection—never another service database.
4. AI only obtains context through tool/API contracts and returns suggestions. All business mutations go through the owning service after user approval.
5. Keep unfinished work as a clear skeleton with a service README and explicit TODOs; never label it implemented.
6. Update contracts, tests, and service/root README when an API or event changes.
7. Run the relevant formatter, lint, tests, and build before handing off. Do not commit secrets or `.env` files.
