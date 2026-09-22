# API contracts

OpenAPI is served by implemented Django services at `/api/schema/` and `/api/docs/`. AI schemas are served by FastAPI OpenAPI. Service-local API paths are versioned under `/api/v1/`; Nginx strips its service prefix before forwarding.
