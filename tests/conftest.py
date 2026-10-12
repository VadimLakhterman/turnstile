import uuid
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.app_factory import create_app
from app.core.config import Settings
from app.core.provider import get_gateway_service
from app.domain.gateway_service import GatewayService
from app.domain.models import PaymentVerification, ProxyResponse
from app.providers.db_models import Base, Client
from app.providers.sql_client_repository import SqlClientRepository

CLIENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
INACTIVE_CLIENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ORIGIN_URL = "https://origin.example.com/api"
PLATFORM_WALLET = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453
TX_HASH = "0x" + "ab" * 32


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, PLATFORM_WALLET=PLATFORM_WALLET, USDC_CONTRACT=USDC_CONTRACT, CHAIN_ID=CHAIN_ID)


@pytest.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def seeded_clients(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                Client(
                    id=CLIENT_ID,
                    name="Test API",
                    origin_url=ORIGIN_URL,
                    price_per_request=Decimal("0.01"),
                    pending_balance=Decimal("0"),
                    total_earned=Decimal("0"),
                    is_active=True,
                ),
                Client(
                    id=INACTIVE_CLIENT_ID,
                    name="Inactive",
                    origin_url=ORIGIN_URL,
                    price_per_request=Decimal("0.01"),
                    pending_balance=Decimal("0"),
                    total_earned=Decimal("0"),
                    is_active=False,
                ),
            ]
        )
        await session.commit()


@pytest.fixture
def client_repository(session_factory: async_sessionmaker[AsyncSession], seeded_clients: None) -> SqlClientRepository:
    return SqlClientRepository(session_factory)


@pytest.fixture
def mock_verifier() -> AsyncMock:
    verifier = AsyncMock()
    verifier.verify.return_value = PaymentVerification(verified=True, amount=Decimal("0.01"))
    return verifier


@pytest.fixture
def mock_proxy() -> AsyncMock:
    proxy = AsyncMock()
    proxy.forward.return_value = ProxyResponse(
        status_code=200, content=b'{"proxied": true}', headers={"content-type": "application/json"}
    )
    return proxy


@pytest.fixture
def gateway_service(client_repository: SqlClientRepository, mock_verifier: AsyncMock, mock_proxy: AsyncMock) -> GatewayService:
    return GatewayService(
        clients=client_repository,
        verifier=mock_verifier,
        proxy=mock_proxy,
        platform_wallet=PLATFORM_WALLET,
        usdc_contract=USDC_CONTRACT,
        chain_id=CHAIN_ID,
    )


@pytest.fixture
def app(settings: Settings, gateway_service: GatewayService) -> Iterator[FastAPI]:
    """App wired to the in-memory DB and mocked verifier/proxy. Lifespan is not run, so no real IO."""
    application = create_app(settings)
    application.dependency_overrides[get_gateway_service] = lambda: gateway_service
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def http_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
