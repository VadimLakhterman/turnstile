"""Dependency wiring: builds providers and the domain service for the app's lifetime."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from app.core.config import Settings
from app.domain.gateway_service import GatewayService
from app.providers.database import create_engine, create_session_factory, init_schema
from app.providers.httpx_origin_proxy import HttpxOriginProxy
from app.providers.sql_client_repository import SqlClientRepository
from app.providers.web3_payment_verifier import Web3PaymentVerifier


def build_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.DATABASE_URL)
        try:
            await init_schema(engine)
            async with httpx.AsyncClient() as http_client:
                app.state.gateway_service = GatewayService(
                    clients=SqlClientRepository(create_session_factory(engine)),
                    verifier=Web3PaymentVerifier(settings.BASE_RPC_URL, settings.USDC_CONTRACT),
                    proxy=HttpxOriginProxy(http_client),
                    platform_wallet=settings.PLATFORM_WALLET,
                    usdc_contract=settings.USDC_CONTRACT,
                    chain_id=settings.CHAIN_ID,
                )
                yield
        finally:
            await engine.dispose()

    return lifespan


def get_gateway_service(request: Request) -> GatewayService:
    service: GatewayService = request.app.state.gateway_service
    return service
