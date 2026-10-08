from dataclasses import dataclass
from decimal import Decimal

from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

# ERC-20 Transfer event signature: Transfer(address,address,uint256)
TRANSFER_EVENT_SIGNATURE = AsyncWeb3.keccak(text="Transfer(address,address,uint256)")

# USDC has 6 decimals
USDC_DECIMALS = 6


@dataclass
class VerificationResult:
    verified: bool
    amount: Decimal
    error: str | None = None


async def verify_usdc_payment(
    tx_hash: str,
    expected_recipient: str,
    min_amount: Decimal,
    rpc_url: str,
    usdc_contract: str,
) -> VerificationResult:
    """Verify a USDC transfer on Base L2 by inspecting transaction receipt logs."""
    w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))

    try:
        receipt = await w3.eth.get_transaction_receipt(tx_hash)
    except Exception as e:
        return VerificationResult(verified=False, amount=Decimal(0), error=f"Failed to fetch receipt: {e}")

    if receipt["status"] != 1:
        return VerificationResult(verified=False, amount=Decimal(0), error="Transaction failed on-chain")

    usdc_address = AsyncWeb3.to_checksum_address(usdc_contract)
    recipient_address = AsyncWeb3.to_checksum_address(expected_recipient)

    for log in receipt["logs"]:
        if AsyncWeb3.to_checksum_address(log["address"]) != usdc_address:
            continue
        if len(log["topics"]) < 3:
            continue
        if log["topics"][0] != TRANSFER_EVENT_SIGNATURE:
            continue

        # topics[2] is the `to` address (zero-padded to 32 bytes)
        to_address = AsyncWeb3.to_checksum_address("0x" + log["topics"][2].hex()[-40:])
        if to_address != recipient_address:
            continue

        raw_amount = int(log["data"].hex(), 16)
        amount = Decimal(raw_amount) / Decimal(10**USDC_DECIMALS)

        if amount < min_amount:
            return VerificationResult(verified=False, amount=amount, error=f"Insufficient payment: {amount} < {min_amount}")

        return VerificationResult(verified=True, amount=amount)

    return VerificationResult(verified=False, amount=Decimal(0), error="No matching USDC transfer found in transaction logs")
