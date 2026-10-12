from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from web3.exceptions import TransactionNotFound

from app.domain.errors import PaymentVerifierUnavailableError
from app.providers.web3_payment_verifier import TRANSFER_EVENT_SIGNATURE, Web3PaymentVerifier
from tests.conftest import PLATFORM_WALLET, TX_HASH, USDC_CONTRACT

RPC_URL = "https://rpc.invalid"


def _make_transfer_log(to_address: str, amount_raw: int, contract: str = USDC_CONTRACT) -> dict[str, Any]:
    """Build a mock ERC-20 Transfer log entry."""
    return {
        "address": contract,
        "topics": [TRANSFER_EVENT_SIGNATURE, bytes(32), bytes.fromhex(to_address[2:].lower().zfill(64))],
        "data": amount_raw.to_bytes(32, "big"),
    }


def _verifier(receipt: dict[str, Any] | None = None, error: Exception | None = None) -> tuple[Web3PaymentVerifier, AsyncMock]:
    verifier = Web3PaymentVerifier(RPC_URL, USDC_CONTRACT)
    get_receipt = AsyncMock(return_value=receipt, side_effect=error)
    verifier._w3 = MagicMock()
    verifier._w3.eth.get_transaction_receipt = get_receipt
    return verifier, get_receipt


async def test_valid_transfer() -> None:
    verifier, get_receipt = _verifier({"status": 1, "logs": [_make_transfer_log(PLATFORM_WALLET, 10_000)]})
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is True
    assert result.amount == Decimal("0.01")
    get_receipt.assert_awaited_once_with(TX_HASH)


async def test_wrong_recipient() -> None:
    log = _make_transfer_log("0x1234567890123456789012345678901234567890", 10_000)
    verifier, _ = _verifier({"status": 1, "logs": [log]})
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False
    assert result.error is not None and "No matching" in result.error


async def test_wrong_token_contract() -> None:
    log = _make_transfer_log(PLATFORM_WALLET, 10_000, contract="0x0000000000000000000000000000000000000001")
    verifier, _ = _verifier({"status": 1, "logs": [log]})
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False


async def test_insufficient_amount() -> None:
    verifier, _ = _verifier({"status": 1, "logs": [_make_transfer_log(PLATFORM_WALLET, 5_000)]})
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False
    assert result.error is not None and "Insufficient" in result.error


async def test_failed_transaction() -> None:
    verifier, _ = _verifier({"status": 0, "logs": [_make_transfer_log(PLATFORM_WALLET, 10_000)]})
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False
    assert result.error is not None and "failed on-chain" in result.error


async def test_invalid_tx_hash_rejected_without_rpc_call() -> None:
    verifier, get_receipt = _verifier()
    result = await verifier.verify("0xabc", PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False
    assert result.error == "Invalid transaction hash"
    get_receipt.assert_not_called()


async def test_unknown_transaction_is_rejected() -> None:
    verifier, _ = _verifier(error=TransactionNotFound("not found"))
    result = await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert result.verified is False
    assert result.error == "Transaction not found"


async def test_rpc_error_raises_unavailable() -> None:
    """Regression: RPC outages used to surface as 400 'verification failed' instead of 502."""
    verifier, _ = _verifier(error=TimeoutError("RPC timeout"))
    with pytest.raises(PaymentVerifierUnavailableError) as exc_info:
        await verifier.verify(TX_HASH, PLATFORM_WALLET, Decimal("0.01"))
    assert isinstance(exc_info.value.__cause__, TimeoutError)
