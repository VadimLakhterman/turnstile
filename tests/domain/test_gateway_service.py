from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.errors import (
    ClientNotFoundError,
    PaymentRequiredError,
    PaymentVerificationFailedError,
    TransactionAlreadyUsedError,
)
from app.domain.gateway_service import GatewayService
from app.domain.models import GatewayClient, PaymentVerification, ProxyRequest, ProxyResponse

CLIENT = GatewayClient(id=uuid4(), origin_url="https://origin.test", price_per_request=Decimal("0.05"))
WALLET = "0xwallet"
TX = "0x" + "cd" * 32
REQUEST = ProxyRequest(headers={"Content-Type": "application/json", "X-Payment": TX, "Cookie": "c"}, params={}, body=b"")


@pytest.fixture
def clients() -> AsyncMock:
    repo = AsyncMock()
    repo.get_active_client.return_value = CLIENT
    repo.is_transaction_used.return_value = False
    return repo


@pytest.fixture
def verifier() -> AsyncMock:
    v = AsyncMock()
    v.verify.return_value = PaymentVerification(verified=True, amount=Decimal("0.05"))
    return v


@pytest.fixture
def proxy() -> AsyncMock:
    p = AsyncMock()
    p.forward.return_value = ProxyResponse(status_code=200, content=b"ok")
    return p


@pytest.fixture
def service(clients: AsyncMock, verifier: AsyncMock, proxy: AsyncMock) -> GatewayService:
    return GatewayService(clients, verifier, proxy, platform_wallet=WALLET, usdc_contract="0xusdc", chain_id=8453)


async def test_get_payment_instructions_uses_client_price(service: GatewayService) -> None:
    instructions = await service.get_payment_instructions(CLIENT.id)
    assert instructions.address == WALLET
    assert instructions.amount == Decimal("0.05")
    assert instructions.chain_id == 8453
    assert instructions.usdc_contract == "0xusdc"


async def test_unknown_client_raises_not_found(service: GatewayService, clients: AsyncMock) -> None:
    clients.get_active_client.return_value = None
    with pytest.raises(ClientNotFoundError):
        await service.handle_paid_request(CLIENT.id, TX, REQUEST)


async def test_missing_tx_hash_raises_payment_required(service: GatewayService, verifier: AsyncMock) -> None:
    with pytest.raises(PaymentRequiredError) as exc_info:
        await service.handle_paid_request(CLIENT.id, None, REQUEST)
    assert exc_info.value.instructions.amount == Decimal("0.05")
    verifier.verify.assert_not_called()


async def test_used_tx_hash_rejected_before_verification(
    service: GatewayService, clients: AsyncMock, verifier: AsyncMock
) -> None:
    clients.is_transaction_used.return_value = True
    with pytest.raises(TransactionAlreadyUsedError):
        await service.handle_paid_request(CLIENT.id, TX, REQUEST)
    verifier.verify.assert_not_called()


async def test_failed_verification_does_not_record_or_proxy(
    service: GatewayService, clients: AsyncMock, verifier: AsyncMock, proxy: AsyncMock
) -> None:
    verifier.verify.return_value = PaymentVerification(verified=False, amount=Decimal(0), error="nope")
    with pytest.raises(PaymentVerificationFailedError, match="nope"):
        await service.handle_paid_request(CLIENT.id, TX, REQUEST)
    clients.record_payment.assert_not_called()
    proxy.forward.assert_not_called()


async def test_verified_payment_is_recorded_then_proxied(
    service: GatewayService, clients: AsyncMock, verifier: AsyncMock, proxy: AsyncMock
) -> None:
    response = await service.handle_paid_request(CLIENT.id, TX, REQUEST)

    verifier.verify.assert_awaited_once_with(TX, WALLET, Decimal("0.05"))
    clients.record_payment.assert_awaited_once_with(CLIENT.id, TX, Decimal("0.05"))
    proxy.forward.assert_awaited_once_with(
        "https://origin.test", ProxyRequest(headers={"Content-Type": "application/json"}, params={}, body=None)
    )
    assert response.content == b"ok"
