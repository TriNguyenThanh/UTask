# Notification Service

**Status: SKELETON.** This service will own in-app notification records and delivery state. It subscribes to task, GitHub and AI risk events; notification delivery is not embedded in Work Service.

## Current implementation

The Django skeleton has an independent build, health endpoint, test setup and an explicit consumer package boundary. It owns no tables and consumes no Kafka events yet.

## Planned API and events

Planned API: read and mark in-app notifications. Planned subscribed events include `task.assigned`, `task.deadline.approaching`, `task.comment.created`, `task.status.changed`, `github.pull_request.merged`, and `ai.project.risk.detected`.

## Not implemented

Kafka consumer, idempotency, notification persistence, in-app/email/web-push delivery, preferences, retries and user-facing APIs are TODO.
