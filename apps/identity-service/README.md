# Identity Service

**Status: SKELETON.** Owns user accounts, profiles, global roles, refresh-token/session metadata and future OAuth accounts.

## Current implementation

The Django/DRF skeleton has an independent build, health endpoint and test setup. It owns no tables yet and exposes only `GET /healthz`.

## Planned boundary

Planned versioned API: login, refresh, logout, password reset and profile endpoints. It will issue JWT access/refresh tokens; other services validate tokens without reading this database.

## Not implemented

User model, profile, roles, JWT, credential flows, rate limiting, OAuth, migrations, OpenAPI endpoints beyond health, events and authorization integration are TODO.
