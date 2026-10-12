# Turnstile

Crypto-in/fiat-out API gateway for AI agent micropayments (USDC on Base).

## Build & Test

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Architecture

Single FastAPI service following the layered architecture in `developer_guide.md`. AI agents pay USDC on Base to a platform wallet; Turnstile verifies on-chain via web3.py, logs earnings per client in PostgreSQL, and proxies the request to the client's origin API.

### Layers
- `app/api/v1/` — routes only; depends on `core` (DI) and `domain`, never on `providers`
- `app/domain/` — `GatewayService` (business flow), entities, `Protocol` interfaces, domain errors; pure Python
- `app/providers/` — `SqlClientRepository` (+ ORM models), `Web3PaymentVerifier`, `HttpxOriginProxy`; wrap SDK errors into domain errors, never log
- `app/core/` — config, `create_app`, lifespan wiring (`provider.py`), error handlers (`errors.py`, the only place errors are logged), correlation-ID middleware
- `app/schemas/` — Pydantic API models

Tests mirror `app/`; the API tests override `get_gateway_service` with a service wired to in-memory SQLite and mocked verifier/proxy.

## Environment Variables

See `.env.example`. Key vars: `DATABASE_URL`, `PLATFORM_WALLET`, `BASE_RPC_URL`.
