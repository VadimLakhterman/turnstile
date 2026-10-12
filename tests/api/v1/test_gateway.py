import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.domain.errors import LedgerWriteError, PaymentVerifierUnavailableError, UpstreamUnavailableError
from app.domain.models import PaymentVerification, ProxyRequest, ProxyResponse
from app.providers.sql_client_repository import SqlClientRepository
from tests.conftest import CLIENT_ID, INACTIVE_CLIENT_ID, ORIGIN_URL, PLATFORM_WALLET, TX_HASH, USDC_CONTRACT

GATEWAY_URL = f"/v1/gateway/{CLIENT_ID}"

EXPECTED_PAYMENT = {
    "address": PLATFORM_WALLET,
    "amount": "0.010000",
    "currency": "USDC",
    "network": "base",
    "chain_id": 8453,
    "usdc_contract": USDC_CONTRACT,
}


async def test_get_payment_instructions(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.get(GATEWAY_URL)
    assert resp.status_code == 200
    assert resp.json() == {"x402_version": 1, "payment": EXPECTED_PAYMENT}


async def test_get_payment_instructions_unknown_client(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.get(f"/v1/gateway/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "Client not found"


async def test_402_when_no_payment_header(http_client: httpx.AsyncClient, mock_verifier: AsyncMock) -> None:
    resp = await http_client.post(GATEWAY_URL)
    assert resp.status_code == 402
    assert resp.json() == {"x402_version": 1, "payment": EXPECTED_PAYMENT}
    mock_verifier.verify.assert_not_called()


async def test_404_for_unknown_client(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.post(f"/v1/gateway/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "Client not found"


async def test_404_for_inactive_client(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.post(f"/v1/gateway/{INACTIVE_CLIENT_ID}", headers={"X-Payment": TX_HASH})
    assert resp.status_code == 404


async def test_422_for_invalid_uuid(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.post("/v1/gateway/not-a-uuid")
    assert resp.status_code == 422


async def test_400_when_verification_fails(http_client: httpx.AsyncClient, mock_verifier: AsyncMock) -> None:
    mock_verifier.verify.return_value = PaymentVerification(verified=False, amount=Decimal(0), error="Insufficient payment")
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "Payment verification failed"
    assert body["detail"] == "Insufficient payment"


async def test_409_for_duplicate_tx_hash(http_client: httpx.AsyncClient) -> None:
    resp1 = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp1.status_code == 200

    resp2 = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp2.status_code == 409
    assert resp2.json()["error"] == "Transaction already used"
    assert resp2.json()["detail"] == TX_HASH


async def test_502_when_verifier_unavailable(http_client: httpx.AsyncClient, mock_verifier: AsyncMock) -> None:
    mock_verifier.verify.side_effect = PaymentVerifierUnavailableError("rpc down")
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp.status_code == 502
    assert resp.json()["error"] == "Payment verification temporarily unavailable"
    assert "rpc down" not in resp.text


async def test_500_when_ledger_write_fails(
    http_client: httpx.AsyncClient, mock_proxy: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SqlClientRepository, "record_payment", AsyncMock(side_effect=LedgerWriteError("db down")))
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp.status_code == 500
    assert resp.json()["error"] == "Internal error recording payment"
    mock_proxy.forward.assert_not_called()


async def test_502_when_upstream_unavailable(http_client: httpx.AsyncClient, mock_proxy: AsyncMock) -> None:
    mock_proxy.forward.side_effect = UpstreamUnavailableError("connect timeout")
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})
    assert resp.status_code == 502
    assert resp.json()["error"] == "Upstream service unavailable"


async def test_successful_proxy_forwards_exact_payload(http_client: httpx.AsyncClient, mock_proxy: AsyncMock) -> None:
    mock_proxy.forward.return_value = ProxyResponse(
        status_code=201, content=b'{"result": "hello"}', headers={"content-type": "application/json", "x-origin": "1"}
    )

    resp = await http_client.post(
        f"{GATEWAY_URL}?q=1",
        headers={"X-Payment": TX_HASH, "Content-Type": "application/json", "Cookie": "secret=1", "Authorization": "Bearer t"},
        content=b'{"prompt": "hi"}',
    )

    assert resp.status_code == 201
    assert resp.json() == {"result": "hello"}
    assert resp.headers["x-origin"] == "1"
    mock_proxy.forward.assert_awaited_once()
    url, forwarded = mock_proxy.forward.await_args.args
    assert url == ORIGIN_URL
    assert isinstance(forwarded, ProxyRequest)
    assert forwarded.params == {"q": "1"}
    assert forwarded.body == b'{"prompt": "hi"}'
    assert forwarded.headers["content-type"] == "application/json"
    assert forwarded.headers["authorization"] == "Bearer t"
    assert "cookie" not in forwarded.headers
    assert "x-payment" not in forwarded.headers
