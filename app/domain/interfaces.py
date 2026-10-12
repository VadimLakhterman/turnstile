"""Ports implemented by app/providers/."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.models import GatewayClient, PaymentVerification, ProxyRequest, ProxyResponse


class ClientRepository(Protocol):
    async def get_active_client(self, client_id: UUID) -> GatewayClient | None: ...

    async def is_transaction_used(self, tx_hash: str) -> bool: ...

    async def record_payment(self, client_id: UUID, tx_hash: str, amount: Decimal) -> None:
        """Persist the ledger entry and credit the client atomically.

        Raises TransactionAlreadyUsedError if tx_hash was recorded concurrently, LedgerWriteError otherwise.
        """
        ...


class PaymentVerifier(Protocol):
    async def verify(self, tx_hash: str, recipient: str, min_amount: Decimal) -> PaymentVerification:
        """Raises PaymentVerifierUnavailableError if the chain cannot be queried."""
        ...


class OriginProxy(Protocol):
    async def forward(self, url: str, request: ProxyRequest) -> ProxyResponse:
        """Raises UpstreamUnavailableError if the origin cannot be reached."""
        ...
