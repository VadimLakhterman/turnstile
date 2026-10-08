# Turnstile

Crypto-in/fiat-out API gateway for AI agent micropayments (USDC on Base).

## Build & Test

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Architecture

Single FastAPI service with a wildcard gateway route. AI agents pay USDC on Base to a platform wallet; Turnstile verifies on-chain via web3.py, logs earnings per client in PostgreSQL, and proxies the request to the client's origin API.

### Key Files
- `app/main.py` — FastAPI app, gateway route
- `app/verifier.py` — On-chain USDC transfer verification
- `app/models.py` — SQLAlchemy models (Client, TransactionLedger)
- `app/config.py` — Pydantic Settings
- `app/database.py` — Async SQLAlchemy engine/session

## Environment Variables

See `.env.example`. Key vars: `DATABASE_URL`, `PLATFORM_WALLET`, `BASE_RPC_URL`.
