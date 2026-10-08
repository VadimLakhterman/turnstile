import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx as httpx_lib
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, Client


@pytest.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_client_record(async_engine):
    """Create a test Client row and return it."""
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        client = Client(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="Test API",
            origin_url="https://httpbin.org",
            price_per_request=Decimal("0.01"),
            pending_balance=Decimal("0"),
            total_earned=Decimal("0"),
            payout_frequency="monthly",
            is_active=True,
        )
        session.add(client)
        await session.commit()
    return client


@pytest.fixture
def app_with_db(async_engine, test_client_record):
    """Create a FastAPI test app wired to the in-memory DB."""
    from app.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def http_client(app_with_db):
    """HTTPX AsyncClient bound to the test app."""
    return httpx_lib.AsyncClient(transport=httpx_lib.ASGITransport(app=app_with_db), base_url="http://test")


@pytest.fixture
def mock_upstream(app_with_db):
    """Mock upstream HTTP client on app.state to avoid real origin calls."""
    mock_response = httpx_lib.Response(200, json={"proxied": True}, headers={"content-type": "application/json"})
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    app_with_db.state.http_client = mock_client
    return mock_client


@pytest.fixture
def mock_verify_success():
    from app.verifier import VerificationResult

    result = VerificationResult(verified=True, amount=Decimal("0.01"))
    with patch("app.main.verify_usdc_payment", new_callable=AsyncMock, return_value=result) as mock:
        yield mock


@pytest.fixture
def mock_verify_failure():
    from app.verifier import VerificationResult

    result = VerificationResult(verified=False, amount=Decimal("0"), error="No matching USDC transfer found")
    with patch("app.main.verify_usdc_payment", new_callable=AsyncMock, return_value=result) as mock:
        yield mock
