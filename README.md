# Turnstile

Crypto-in/fiat-out API gateway for AI agent micropayments. AI agents pay USDC on Base to access your API — Turnstile verifies the payment on-chain and proxies the request to your origin server.

## How It Works

```
AI Agent                        Turnstile                         Your API
   │                               │                                 │
   │  GET /v1/gateway/{client_id}  │                                 │
   │──────────────────────────────>│                                 │
   │  200: wallet, price, network  │                                 │
   │<──────────────────────────────│                                 │
   │                               │                                 │
   │  (pay USDC on Base)           │                                 │
   │                               │                                 │
   │  POST /v1/gateway/{client_id} │                                 │
   │  X-Payment: 0xtxhash...      │                                 │
   │  + request body               │                                 │
   │──────────────────────────────>│  verify tx on-chain             │
   │                               │  record in ledger               │
   │                               │  POST origin_url                │
   │                               │────────────────────────────────>│
   │                               │             response            │
   │          proxied response     │<────────────────────────────────│
   │<──────────────────────────────│                                 │
```

1. Agent discovers payment details via `GET /v1/gateway/{client_id}`
2. Agent sends USDC to the platform wallet on Base
3. Agent calls `POST /v1/gateway/{client_id}` with the tx hash in `X-Payment` header
4. Turnstile verifies the transfer on-chain, records it, and proxies the request to the origin

## API

### `GET /v1/gateway/{client_id}`

Returns payment instructions. No authentication required.

```json
{
  "x402_version": 1,
  "payment": {
    "address": "0x...",
    "amount": "0.01",
    "currency": "USDC",
    "network": "base",
    "chain_id": 8453,
    "usdc_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
  }
}
```

### `POST /v1/gateway/{client_id}`

Requires `X-Payment` header containing the USDC transaction hash. Returns:

| Status | Meaning |
|--------|---------|
| 200 | Payment verified, proxied response from origin |
| 400 | Payment verification failed |
| 402 | Missing `X-Payment` header |
| 404 | Unknown or inactive client |
| 409 | Transaction hash already used |
| 502 | Origin or RPC unavailable |

### `GET /healthz`

Returns `{"status": "ok"}`.

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL
- A Base RPC endpoint (public `https://mainnet.base.org` works, or use Alchemy/Infura)
- A wallet address to receive USDC payments

### Local Development

```bash
# Install dependencies
uv sync --extra dev

# Configure environment
cp .env.example .env
# Edit .env — set PLATFORM_WALLET at minimum

# Start PostgreSQL (if not using Docker)
# Tables are auto-created on startup

# Run the server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check .
```

### Docker Compose

```bash
cp .env.example .env
# Edit .env — set PLATFORM_WALLET

docker compose up --build -d

# Verify
curl localhost:8000/healthz
```

This starts PostgreSQL and the API server. The database schema is created automatically on startup.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://turnstile:turnstile@localhost:5432/turnstile` | Async PostgreSQL connection string |
| `PLATFORM_WALLET` | _(required)_ | Wallet address that receives USDC payments (must start with `0x`) |
| `BASE_RPC_URL` | `https://mainnet.base.org` | Base L2 RPC endpoint for on-chain verification |
| `USDC_CONTRACT` | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | USDC token contract address on Base |
| `DEFAULT_PRICE_USD` | `0.01` | Default price per request in USD |
| `CHAIN_ID` | `8453` | Chain ID returned in payment instructions |

## Project Structure

```
app/
  main.py        — FastAPI app, gateway routes, proxy logic
  verifier.py    — On-chain USDC transfer verification via web3.py
  models.py      — SQLAlchemy models (Client, TransactionLedger)
  schemas.py     — Pydantic request/response models
  config.py      — Settings from environment variables
  database.py    — Async SQLAlchemy engine and session
tests/
  test_gateway.py  — Gateway route tests
  test_verifier.py — On-chain verification tests
```
