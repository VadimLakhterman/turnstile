import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine, get_db, init_db
from app.models import Client, TransactionLedger
from app.schemas import GatewayErrorResponse, PaymentInfo, PaymentRequiredResponse
from app.verifier import verify_usdc_payment

logger = logging.getLogger(__name__)

FORWARD_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "authorization",
        "cache-control",
        "content-type",
        "user-agent",
    }
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with httpx.AsyncClient() as client:
        app.state.http_client = client
        yield
    await engine.dispose()


app = FastAPI(title="Turnstile", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


async def _get_client(client_id: UUID, db: AsyncSession) -> Client | None:
    result = await db.execute(select(Client).where(Client.id == client_id, Client.is_active.is_(True)))
    return result.scalar_one_or_none()


@app.get("/v1/gateway/{client_id}")
async def gateway_info(client_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return payment instructions for this client's gateway."""
    client = await _get_client(client_id, db)
    if client is None:
        return JSONResponse(status_code=404, content=GatewayErrorResponse(error="Client not found").model_dump())

    price = Decimal(str(client.price_per_request))
    body = PaymentRequiredResponse(
        payment=PaymentInfo(
            address=settings.PLATFORM_WALLET,
            amount=str(price),
            usdc_contract=settings.USDC_CONTRACT,
        )
    )
    return JSONResponse(status_code=200, content=body.model_dump())


@app.post("/v1/gateway/{client_id}")
async def gateway(client_id: UUID, request: Request, db: AsyncSession = Depends(get_db)):
    """Verify payment and proxy request to client's origin."""
    client = await _get_client(client_id, db)
    if client is None:
        return JSONResponse(status_code=404, content=GatewayErrorResponse(error="Client not found").model_dump())

    price = Decimal(str(client.price_per_request))

    # Check for payment header
    tx_hash = request.headers.get("X-Payment")
    if not tx_hash:
        body = PaymentRequiredResponse(
            payment=PaymentInfo(
                address=settings.PLATFORM_WALLET,
                amount=str(price),
                usdc_contract=settings.USDC_CONTRACT,
            )
        )
        return JSONResponse(status_code=402, content=body.model_dump())

    # Check for duplicate tx_hash
    existing = await db.execute(select(TransactionLedger).where(TransactionLedger.tx_hash == tx_hash))
    if existing.scalar_one_or_none() is not None:
        return JSONResponse(
            status_code=409,
            content=GatewayErrorResponse(error="Transaction already used", detail=tx_hash).model_dump(),
        )

    # Verify on-chain payment
    logger.info("Verifying payment tx_hash=%s client_id=%s", tx_hash, client_id)
    try:
        verification = await verify_usdc_payment(
            tx_hash=tx_hash,
            expected_recipient=settings.PLATFORM_WALLET,
            min_amount=price,
            rpc_url=settings.BASE_RPC_URL,
            usdc_contract=settings.USDC_CONTRACT,
        )
    except Exception:
        logger.exception("RPC error during payment verification tx_hash=%s", tx_hash)
        return JSONResponse(
            status_code=502,
            content=GatewayErrorResponse(error="Payment verification temporarily unavailable").model_dump(),
        )

    if not verification.verified:
        return JSONResponse(
            status_code=400,
            content=GatewayErrorResponse(error="Payment verification failed", detail=verification.error).model_dump(),
        )

    # Record transaction and credit client
    ledger_entry = TransactionLedger(
        tx_hash=tx_hash,
        amount_usdc=verification.amount,
        client_id=client.id,
    )
    db.add(ledger_entry)
    client.pending_balance = Decimal(str(client.pending_balance)) + verification.amount
    client.total_earned = Decimal(str(client.total_earned)) + verification.amount
    try:
        await db.commit()
    except Exception:
        logger.exception("Failed to commit ledger entry tx_hash=%s", tx_hash)
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content=GatewayErrorResponse(error="Internal error recording payment").model_dump(),
        )

    # Proxy request to origin
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS}
    body = await request.body()

    http_client: httpx.AsyncClient = request.app.state.http_client
    logger.info("Proxying to origin=%s client_id=%s", client.origin_url, client_id)
    try:
        upstream_response = await http_client.post(
            url=client.origin_url,
            headers=forward_headers,
            params=dict(request.query_params),
            content=body if body else None,
        )
    except httpx.HTTPError:
        logger.exception("Upstream request failed origin=%s", client.origin_url)
        return JSONResponse(
            status_code=502,
            content=GatewayErrorResponse(error="Upstream service unavailable").model_dump(),
        )

    skip_headers = {"transfer-encoding", "content-encoding"}
    resp_headers = {k: v for k, v in upstream_response.headers.items() if k.lower() not in skip_headers}

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=resp_headers,
    )
