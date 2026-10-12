import re
from decimal import Decimal

from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound
from web3.providers import AsyncHTTPProvider

from app.domain.errors import PaymentVerifierUnavailableError
from app.domain.models import PaymentVerification

# ERC-20 Transfer event signature: Transfer(address,address,uint256)
TRANSFER_EVENT_SIGNATURE = AsyncWeb3.keccak(text="Transfer(address,address,uint256)")

# USDC has 6 decimals
USDC_DECIMALS = 6

TX_HASH_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")


class Web3PaymentVerifier:
    """PaymentVerifier that inspects USDC Transfer logs in a Base L2 transaction receipt."""

    def __init__(self, rpc_url: str, usdc_contract: str) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self._usdc_contract = usdc_contract

    async def verify(self, tx_hash: str, recipient: str, min_amount: Decimal) -> PaymentVerification:
        if not TX_HASH_PATTERN.match(tx_hash):
            return _rejected("Invalid transaction hash")

        try:
            receipt = await self._w3.eth.get_transaction_receipt(tx_hash)  # type: ignore[arg-type]
        except TransactionNotFound:
            return _rejected("Transaction not found")
        except Exception as exc:
            raise PaymentVerifierUnavailableError(f"Failed to fetch receipt tx_hash={tx_hash}") from exc

        if receipt["status"] != 1:
            return _rejected("Transaction failed on-chain")

        usdc_address = AsyncWeb3.to_checksum_address(self._usdc_contract)
        recipient_address = AsyncWeb3.to_checksum_address(recipient)

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
                return PaymentVerification(verified=False, amount=amount, error=f"Insufficient payment: {amount} < {min_amount}")

            return PaymentVerification(verified=True, amount=amount)

        return _rejected("No matching USDC transfer found in transaction logs")


def _rejected(error: str) -> PaymentVerification:
    return PaymentVerification(verified=False, amount=Decimal(0), error=error)
