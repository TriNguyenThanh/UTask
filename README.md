<div align="center">

# UTask

### Agile Project Management for Student Teams

**Plan projects, track sprint progress, and review AI suggestions in an academic workspace.**

![React](https://img.shields.io/badge/React-Frontend-61DAFB)
![Django REST Framework](https://img.shields.io/badge/Django_REST_Framework-Domain_APIs-092E20)
![FastAPI](https://img.shields.io/badge/FastAPI-AI_Service-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-336791)
![Google ADK](https://img.shields.io/badge/Google_ADK-AI_Agent-4285F4)
![Docker](https://img.shields.io/badge/Docker-Containers-2496ED)

</div>

---

## Overview

**UTask** is a project management platform being developed for students and instructors working on software projects. It brings Scrum and Agile workflows into a classroom setting, connecting courses and teams with project planning, task tracking, and progress reporting.

The AI Service supports planning and analysis by producing suggestions for users to review. The target design keeps progress calculations in the Work Service, using defined rules independently of AI.

**Repository status: Partial.** The repository contains a React web application with mock API support and Identity, Classroom, and Work Django backends, plus an AI Service with a request API, PostgreSQL persistence, a dispatcher, and Celery workers. Local startup is documented separately; integration acceptance and production LLM behavior remain unverified unless recorded in service validation reports.

---

## Planned Capabilities

The following areas describe the product scope and target architecture.

| Area                | Scope                                                        |
| ------------------- | ------------------------------------------------------------ |
| Classroom and Teams | Organize courses, classes, groups, and student participation |
| Project Management  | Manage projects, members, tasks, comments, and workflows     |
| Backlog Planning    | Organize epics, user stories, priorities, and story points   |
| Sprint and Kanban   | Plan sprints and track work through a configurable board     |
| Progress Tracking   | Calculate task and project progress using defined rules      |
| GitHub Integration  | Connect repositories and link development activity to tasks  |
| AI Assistance       | Draft backlogs, break down tasks, and explain delivery risks |
| Notifications       | Keep users informed about relevant changes and activity      |

---

## AI Assistance

The first version of the AI API supports three intents:

### Backlog Generation

Draft a backlog from a project or feature description for the team to review and refine.

### Task Decomposition

Break a complex task into smaller subtasks using the available task context.

### Risk Analysis

Identify and explain risks that may affect a sprint or deadline using relevant project context.

AI requests are processed through a bounded workflow with output validation and execution limits. Context is obtained through domain tools backed by internal APIs.

> **User review:** AI produces proposals for users to review. Applying confirmed changes belongs to the service that owns the data, which must check permissions and business rules.

See the [AI Service documentation](docs/ai-service/README.md) for setup and API scope, and the [code map](docs/ai-service/code-map.md) for implementation details and verification limits.

---

## Technology Stack

React and the AI Service dependencies are present in the repository. The remaining platform choices follow the [architecture baseline](docs/architecture/README.md).

| Layer               | Technology                              | Scope                          |
| ------------------- | --------------------------------------- | ------------------------------ |
| **Frontend**        | React · Vite · TypeScript               | Web application                |
| **Domain APIs**     | Python · Django · Django REST Framework | Identity, Classroom, and Work services |
| **AI API**          | FastAPI · Pydantic                      | AI requests and validation     |
| **AI Runtime**      | Google ADK · Gemini                     | Agent workflow and provider    |
| **Database**        | PostgreSQL                              | Separate database per service  |
| **Background Jobs** | Celery · Redis                          | Internal service jobs          |
| **Events**          | Kafka                                   | Planned events across services |
| **File Storage**    | Cloudflare R2                           | Planned production storage     |
| **Testing**         | pytest · Vitest · React Testing Library | Backend and frontend tests     |
| **Infrastructure**  | Docker Compose · Nginx                  | Local stacks and API routing   |

---

## System Architecture

**Target design.** UTask separates services by business responsibility. The diagram shows the intended platform structure.

```text
React Web Application
        │ REST
        ▼
Nginx / Reverse Proxy
        ├── Identity Service       Authentication and user profiles
        ├── Work Service           Projects, tasks, sprints, and progress
        ├── Classroom Service      Courses, classes, and groups
        ├── Integration Service    GitHub connection and activity
        └── Notification Service   Notifications and delivery

Internal AI Service
        ├── Domain APIs            Authorized project context via REST
        └── LLM Provider           Google ADK

Infrastructure: PostgreSQL · Redis · Kafka · Cloudflare R2
```

Each service owns its data and exposes it through agreed APIs or events. REST handles requests that need a direct response; Kafka carries asynchronous events between services. Celery and Redis handle jobs within a service.

The AI Service provides analysis and proposals without direct access to other services' databases. The Integration Service is the only service that calls the GitHub API.

See [system architecture](docs/system/architecture.md) and [data ownership](docs/system/data-ownership.md) for the service boundaries and current decisions.

---

## Repository Structure

```text
UTask/
│
├── apps/
│   ├── web/                 # React + Vite application
│   └── ai-service/          # Internal AI Service
│
├── contracts/
│   ├── api/                 # Machine-readable API contracts
│   └── events/              # Event contracts; check baseline compatibility
│
├── datasets/               # AI evaluation and example data
├── docs/                   # System, service, and infrastructure documentation
├── infra/                  # Nginx, PostgreSQL, and environment configuration
├── scripts/                # Development and CI utilities
├── docker-compose.yml      # Local infrastructure and default Identity–Classroom–Work stack
└── README.md
```

---

## Development and Documentation

Start with the [documentation overview](docs/system/README.md). Detailed developer documentation is maintained in Vietnamese under `docs/`.

| Resource                                             | Purpose                                        |
| ---------------------------------------------------- | ---------------------------------------------- |
| [Architecture Baseline](docs/architecture/README.md) | Technology choices and target service design   |
| [Development Guide](docs/system/development.md)      | Repository conventions and verification        |
| [Web Application](apps/web/README.md)                | Frontend setup and local commands              |
| [AI Service](docs/ai-service/README.md)              | Configuration, local stack, and quality checks |
| [AI Implementation Map](docs/ai-service/code-map.md) | Source locations and integration limits        |
| [Infrastructure](docs/infrastructure/README.md)      | Environment, storage, messaging, and CI/CD     |
| [Architecture Decisions](docs/adr/README.md)         | Recorded decisions and changes to the baseline |

Use the [local development guide](docs/infrastructure/local-development.md) for the default Identity–Classroom–Work stack and its environment prerequisites. Those three API containers apply database migrations at startup; Docker builds only prepare images. The Web app has separate setup instructions, and AI/other optional services require their documented profiles and configuration.

---

<div align="center">

### UTask

**Project planning and progress tracking for student teams.**

</div>
