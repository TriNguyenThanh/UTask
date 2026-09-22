# Classroom Service

**Status: SKELETON.** Owns course/subject, class, teacher, student, group, attendance, grade and group-project association data.

## Current implementation

The Django/DRF skeleton has an independent build, health endpoint and test setup. It owns no tables yet and exposes only `GET /healthz`.

## Planned boundary

It will offer versioned class, membership and group context APIs. If AI needs classroom context it must obtain it through those APIs, not a direct database connection.

## Not implemented

Entities, migrations, attendance, grades, Work association API, authentication/authorization, OpenAPI endpoints beyond health and events are TODO.
