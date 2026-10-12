# Developer Guide – Python Repository Standard

### NOTE: These rules define the ideal structure. Tactical violations are allowed but must be documented


## 1. Overview

### Purpose

This repository follows the organization standard for Python repositories.  
The goal of this standard is to ensure:

- Consistent repository structure across teams
- Clear separation of responsibilities
- Predictable development and deployment workflows
- High testability and maintainability
- Low onboarding friction for new developers

Any developer familiar with this guide should be able to navigate, run, test, and extend the repository with minimal additional context.

---

### Repository Type

This repository must explicitly declare what it is:

- **Service** – long-running process (HTTP API, worker, scheduler)
- **Library** – imported by other Python projects
- **Job / Tool** – executed on demand (CLI, batch job)

> Service repositories MUST define an entrypoint and provide Docker and docker-compose configuration.

---

### Design Principles

This repository uses a **layered architecture** with strict boundaries:

- **API layer** – transport concerns only (HTTP, routing, auth, serialization)
- **Domain layer** – business abstractions and errors (framework-agnostic)
- **Providers layer** – external system integrations (cloud, DBs, APIs)
- **Core layer** – application wiring and cross-cutting concerns

Core rules:
- No business logic in API routes or entrypoints
- Domain code must not depend on frameworks or SDKs
- Providers implement domain interfaces
- Entrypoints contain no logic beyond startup

---

## 2. Repository Layout

### Top-Level Structure

```text
repo-root/
├── app/                    # Application source code (single Python package)
├── tests/                  # Automated tests
├── docker/                 # Dockerfiles
├── docker-compose.yml
├── docker-compose.local.yml
├── .env.example
├── pyproject.toml
├── README.md
└── docs/
    └── developer-guide.md
```

### Mandatory Rules

- Exactly one top-level Python package (app/)
- No Python files at repo root
- Docker is mandatory for services
- .env.example must always exist

## 3. Application Package Structure (app/)

```text
app/
├── api/                    # Transport layer (FastAPI / HTTP)
├── core/                   # Application wiring and cross-cutting concerns
├── domain/                 # Business abstractions
├── providers/              # External system implementations
├── schemas/                # API request/response schemas
├── main.py                 # Entrypoint
└── __init__.py
```

Each layer has a clearly defined responsibility.

## 4. API Layer (app/api/)

```text
api/
├── v1/
│   ├── deps.py
│   ├── health.py
│   ├── router.py
│   └── __init__.py
```

### Responsibilities

- Routing
- Authentication / authorization
- Request parsing and validation
- Response serialization

### Rules

- API must be versioned (v1, v2, …)
- No business logic in routes
- API may depend on domain and core
- API must not directly depend on providers

## 5. Core Layer (app/core/)

```text
core/
├── app_factory.py
├── config.py
├── logging_config.py
├── middleware.py
├── provider.py
├── errors.py
```

### Responsibilities

- Application creation and startup
- Dependency injection / wiring
- Configuration loading
- Logging setup
- Middleware
- Global error handling

### Rules

- Core may depend on all other layers
- Core must not contain business logic

## 6. Domain Layer (app/domain/)

```text
domain/
├── interfaces.py
├── errors.py
└── __init__.py
```

### Responsibilities

- Business interfaces (Protocols / ABCs)
- Domain-specific errors
- Pure business abstractions

### Rules (Strict)

- No framework imports
- No SDK imports
- No environment access
- Pure Python only
- If the framework were removed, the domain layer should remain intact.

## 7. Providers Layer (app/providers/)

```text
providers/
├── aws_s3.py
├── azure_blob.py
├── gcs.py
├── minio.py
├── local.py
└── __init__.py
```

### Responsibilities

- Implement domain interfaces
- Handle all external IO
- Use SDKs and external APIs
- Manage retries, timeouts, serialization

### Rules

- Must implement domain interfaces
- Must not depend on API layer
- May depend on core configuration

## 8. Schemas (app/schemas/)

### Purpose

- Request and response models
- Validation and serialization
- API boundary contracts

### Rules

- Schemas are not domain models
- Schemas must not contain business logic
- Schemas are allowed to depend on frameworks

## 9. Entrypoint (app/main.py)

### Purpose

- Application startup only

### Allowed

- Load configuration
- Create application instance
- Start server or process

### Forbidden

- Business logic
- Provider initialization logic
- Direct SDK usage

> If main.py exceeds ~30 lines, it likely violates this rule.

## 10. Configuration & Environment Variables

### Configuration Sources (Priority Order)

1. Environment variables
2. .env file (local development only)
3. Defaults in code

### Rules

- No secrets committed to the repo
- .env must be gitignored
- .env.example must list all required variables
- Configuration access must be centralized

## 11. Docker & Docker Compose

### Dockerfiles

```text
docker/
├── Dockerfile            # Production
├── Dockerfile.local      # Development
```

### Compose

- `docker-compose.yml`
- `docker-compose.local.yml`

### Rules

- Images must be reproducible
- No secrets baked into images
- Local compose may include mocks or emulators
- Production compose must be production-safe

## 12. Testing Strategy

```text
tests/
├── test_providers/
├── test_health.py
├── test_objects.py
├── test_buckets.py
├── conftest.py
```

### Test Types

- Unit tests – fast, isolated, no IO
- Integration tests – explicit, controlled dependencies

### Rules

- Unit tests must not access the network
- Providers must be testable without real cloud access
- CI must run tests by default

## 13. Code Quality Standards

### Required Checks

- Formatting
- Linting
- Type checking
- Tests

These must be enforced in CI.

Repo-specific deviations require explicit approval.

### Must Use Tools

- **pytest** – testing framework
- **mypy** – type checking
- **FastAPI** – web framework (for web services)
- **uvicorn** – ASGI server
- **healthcheck endpoint** – must implement `/healthz` endpoint

### Async/Sync Guidelines

- Use **async** for IO tasks (network calls, database operations, file I/O)
- Use **sync** for standard usage (CPU-bound operations, simple computations)

## 14. Adding New Code

### Where Code Belongs

- Business rules → domain/
- External systems → providers/
- HTTP logic → api/
- Wiring/config → core/

### Design Guidelines

- Prefer composition over inheritance
- Keep functions small and testable
- Avoid framework leakage into domain code

## 15. Error Propagation: Wrap and Raise, Log Once

**Never log and re-raise an error in the same function.** Each layer wraps
the exception with context and raises it. Only the outermost boundary
(error handler / middleware) logs the error and translates it to a client
response.

```text
provider    →  catches SDK exception, raises domain error with context
service     →  adds context if useful, re-raises
error handler → logs once (with correlation ID + tenant), returns HTTP response
```

**Why:**
- If every layer logs, the same error appears 3-4 times in your logs
- Lower layers lack request context (correlation ID, tenant) — only the
  error handler has it
- Chaining with `raise DomainError(...) from exc` preserves the full
  traceback, so the single log entry tells the whole story

```python
# BAD — logs AND raises (duplicates the error at every layer)
class S3ObjectStore:
    async def get(self, key: str) -> ObjectData:
        try:
            resp = await s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            logger.error("failed to get object", exc_info=exc)  # don't do this
            raise ProviderError("s3 get failed") from exc


# GOOD — wrap with context and raise
class S3ObjectStore:
    async def get(self, key: str) -> ObjectData:
        try:
            resp = await s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise ProviderError("s3 get failed") from exc


# The error handler logs the full chain once:
#   "provider error" with correlation_id, full traceback attached
# One log line, full trace, with request context.
```

### Rules

- **Providers**: catch SDK exceptions, raise domain errors (`from exc` to
  preserve the chain). Never log.
- **Services**: re-raise or wrap into a more specific domain error. Never log.
- **Error handlers** (`core/errors.py`): log once with correlation ID, return
  a generic HTTP response to the client.
- Never surface stack traces or internal messages to clients — return a
  correlation ID so operators can look it up.

---

## 16. Common Pitfalls

- Putting logic in main.py
- Accessing environment variables outside config
- Mixing domain and provider logic
- Writing integration tests as unit tests
- Logging an error and also re-raising it (causes duplicate log entries)

## 17. CI/CD Runner Policy

All GitHub Actions workflows must use the correct runner based on job resource requirements.

### Available Runners

| Runner | Type | CPU | RAM | Disk | Use for |
|---|---|---|---|---|---|
| `ubuntu-latest` | Standard GitHub-hosted | 4 | 16 GB | 14 GB | Minimal jobs — checks, labels, notifications, releases |
| `ci-cd-runner` | Larger GitHub-hosted | 8 | 32 GB | 300 GB | Tests, linting, Docker builds, deployments |
| `[self-hosted, qa, linux, x64]` | Self-hosted QA | — | — | — | E2E, automation, load tests, nightly suites |

### Runner Assignment Rules

**`ubuntu-latest`** — Use for jobs that only run API calls, regex checks, or notifications:
- Jira ticket check
- Dependabot label / alert check
- Hotfix release creation
- Platform notify (repository_dispatch)
- Prepare vars
- PR review (Claude) — runner is idle while waiting for API responses
- Daily CI report
- Dependabot digest

**`ci-cd-runner`** — Use for jobs that install dependencies, compile, or build:
- Python unit tests (pytest)
- Python linting (ruff, mypy, pre-commit)
- Node unit tests (Jest)
- Node linting (ESLint)
- Node production builds (TypeScript + Vite)
- Docker build & push to ECR
- Path change detection (`detect-changes` jobs may use `ubuntu-latest`)

**`[self-hosted, qa, linux, x64]`** — Use for jobs that spin up multi-container environments:
- E2E pipeline tests
- Service API / automation tests
- Load tests (Locust)
- Nightly full suite
- Auto-implement (Claude Code with full test suite)

### Rules

- Never use `ubuntu-latest` for jobs that run `pip install`, `yarn install`, `pytest`, `docker build`, or similar
- Never use `ci-cd-runner` for trivial jobs that only make API calls — use `ubuntu-latest` to avoid wasting the larger runner
- QA runner is reserved for jobs that require Docker Compose stacks — do not use it for unit tests or builds
- When adding a new workflow, pick the runner based on the heaviest operation in the job

## 18. Troubleshooting

### Common Issues

- Containers fail to start
- Tests pass locally but fail in Docker
- Port conflicts
- Missing environment variables
