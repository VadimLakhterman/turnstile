from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.verifier import TRANSFER_EVENT_SIGNATURE, verify_usdc_payment

PLATFORM_WALLET = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC_URL = "https://mainnet.base.org"


def _mock_checksum(addr: str) -> str:
    """Normalize addresses to lowercase — simulates consistent checksum behavior for tests."""
    if addr.startswith("0x") and len(addr) == 42:
        return addr.lower()
    return ("0x" + addr[-40:]).lower()


def _make_transfer_log(to_address: str, amount_raw: int, contract: str = USDC_CONTRACT):
    """Build a mock ERC-20 Transfer log entry."""
    to_padded = bytes.fromhex(to_address[2:].lower().zfill(64))
    from_padded = bytes.fromhex("0" * 64)
    data = amount_raw.to_bytes(32, "big")
    return {
        "address": contract,
        "topics": [
            TRANSFER_EVENT_SIGNATURE,
            from_padded,
            to_padded,
        ],
        "data": data,
    }


def _mock_receipt(status: int, logs: list):
    return {"status": status, "logs": logs}


@pytest.mark.asyncio
async def test_valid_transfer():
    amount_raw = 10_000  # 0.01 USDC (6 decimals)
    log = _make_transfer_log(PLATFORM_WALLET, amount_raw)
    receipt = _mock_receipt(1, [log])

    with patch("app.verifier.AsyncWeb3") as MockW3:
        instance = MockW3.return_value
        instance.eth.get_transaction_receipt = AsyncMock(return_value=receipt)
        MockW3.to_checksum_address = _mock_checksum
        MockW3.keccak = lambda text: TRANSFER_EVENT_SIGNATURE

        result = await verify_usdc_payment(
            tx_hash="0xabc",
            expected_recipient=PLATFORM_WALLET,
            min_amount=Decimal("0.01"),
            rpc_url=RPC_URL,
            usdc_contract=USDC_CONTRACT,
        )

    assert result.verified is True
    assert result.amount == Decimal("0.01")


@pytest.mark.asyncio
async def test_wrong_recipient():
    wrong_wallet = "0x1234567890123456789012345678901234567890"
    amount_raw = 10_000
    log = _make_transfer_log(wrong_wallet, amount_raw)
    receipt = _mock_receipt(1, [log])

    with patch("app.verifier.AsyncWeb3") as MockW3:
        instance = MockW3.return_value
        instance.eth.get_transaction_receipt = AsyncMock(return_value=receipt)
        MockW3.to_checksum_address = _mock_checksum
        MockW3.keccak = lambda text: TRANSFER_EVENT_SIGNATURE

        result = await verify_usdc_payment(
            tx_hash="0xabc",
            expected_recipient=PLATFORM_WALLET,
            min_amount=Decimal("0.01"),
            rpc_url=RPC_URL,
            usdc_contract=USDC_CONTRACT,
        )

    assert result.verified is False
    assert "No matching" in result.error


@pytest.mark.asyncio
async def test_insufficient_amount():
    amount_raw = 5_000  # 0.005 USDC — less than 0.01
    log = _make_transfer_log(PLATFORM_WALLET, amount_raw)
    receipt = _mock_receipt(1, [log])

    with patch("app.verifier.AsyncWeb3") as MockW3:
        instance = MockW3.return_value
        instance.eth.get_transaction_receipt = AsyncMock(return_value=receipt)
        MockW3.to_checksum_address = _mock_checksum
        MockW3.keccak = lambda text: TRANSFER_EVENT_SIGNATURE

        result = await verify_usdc_payment(
            tx_hash="0xabc",
            expected_recipient=PLATFORM_WALLET,
            min_amount=Decimal("0.01"),
            rpc_url=RPC_URL,
            usdc_contract=USDC_CONTRACT,
        )

    assert result.verified is False
    assert "Insufficient" in result.error


@pytest.mark.asyncio
async def test_failed_transaction():
    log = _make_transfer_log(PLATFORM_WALLET, 10_000)
    receipt = _mock_receipt(0, [log])  # status 0 = failed

    with patch("app.verifier.AsyncWeb3") as MockW3:
        instance = MockW3.return_value
        instance.eth.get_transaction_receipt = AsyncMock(return_value=receipt)
        MockW3.to_checksum_address = _mock_checksum

        result = await verify_usdc_payment(
            tx_hash="0xabc",
            expected_recipient=PLATFORM_WALLET,
            min_amount=Decimal("0.01"),
            rpc_url=RPC_URL,
            usdc_contract=USDC_CONTRACT,
        )

    assert result.verified is False
    assert "failed on-chain" in result.error.lower()


@pytest.mark.asyncio
async def test_receipt_fetch_error():
    with patch("app.verifier.AsyncWeb3") as MockW3:
        instance = MockW3.return_value
        instance.eth.get_transaction_receipt = AsyncMock(side_effect=Exception("RPC timeout"))

        result = await verify_usdc_payment(
            tx_hash="0xabc",
            expected_recipient=PLATFORM_WALLET,
            min_amount=Decimal("0.01"),
            rpc_url=RPC_URL,
            usdc_contract=USDC_CONTRACT,
        )

    assert result.verified is False
    assert "Failed to fetch" in result.error
