import uuid
from unittest.mock import AsyncMock

import httpx as httpx_lib
import pytest

CLIENT_ID = "11111111-1111-1111-1111-111111111111"
FAKE_TX = "0xabc123def456789012345678901234567890123456789012345678901234abcd"
GATEWAY_URL = f"/v1/gateway/{CLIENT_ID}"


@pytest.mark.asyncio
async def test_get_payment_instructions(http_client):
    resp = await http_client.get(GATEWAY_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["x402_version"] == 1
    assert body["payment"]["currency"] == "USDC"
    assert body["payment"]["network"] == "base"
    assert body["payment"]["amount"] == "0.010000"


@pytest.mark.asyncio
async def test_402_when_no_payment_header(http_client):
    resp = await http_client.post(GATEWAY_URL)
    assert resp.status_code == 402
    body = resp.json()
    assert body["x402_version"] == 1
    assert body["payment"]["currency"] == "USDC"
    assert body["payment"]["network"] == "base"


@pytest.mark.asyncio
async def test_404_for_unknown_client(http_client):
    resp = await http_client.post(f"/v1/gateway/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "Client not found"


@pytest.mark.asyncio
async def test_404_for_invalid_uuid(http_client):
    resp = await http_client.post("/v1/gateway/not-a-uuid")
    assert resp.status_code == 422  # FastAPI validates UUID path param


@pytest.mark.asyncio
async def test_404_for_inactive_client(async_engine, http_client):
    """Inactive clients should return 404."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models import Client

    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    inactive_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    async with session_factory() as session:
        session.add(
            Client(
                id=inactive_id,
                name="Inactive",
                origin_url="https://example.com",
                price_per_request=0.01,
                fiat_balance=0,
                is_active=False,
            )
        )
        await session.commit()

    resp = await http_client.post(f"/v1/gateway/{inactive_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_400_when_verification_fails(http_client, mock_verify_failure):
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": FAKE_TX})
    assert resp.status_code == 400
    assert "verification failed" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_409_for_duplicate_tx_hash(http_client, mock_verify_success, mock_upstream):
    # First request should succeed
    resp1 = await http_client.post(GATEWAY_URL, headers={"X-Payment": FAKE_TX})
    assert resp1.status_code == 200

    # Second request with same tx_hash should be 409
    resp2 = await http_client.post(GATEWAY_URL, headers={"X-Payment": FAKE_TX})
    assert resp2.status_code == 409
    assert "already used" in resp2.json()["error"].lower()


@pytest.mark.asyncio
async def test_successful_proxy(http_client, mock_verify_success, mock_upstream):
    mock_upstream.post = AsyncMock(
        return_value=httpx_lib.Response(200, json={"result": "hello"}, headers={"content-type": "application/json"})
    )

    tx = "0x1111111111111111111111111111111111111111111111111111111111111111"
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": tx})
    assert resp.status_code == 200
    assert resp.json() == {"result": "hello"}

    # Verify proxy was called with the client's origin_url
    call_kwargs = mock_upstream.post.call_args
    assert call_kwargs.kwargs["url"] == "https://httpbin.org"
