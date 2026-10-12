"""Pay-per-request gateway: verify an on-chain payment, record it, proxy to the client's origin."""

from uuid import UUID

from app.domain.errors import (
    ClientNotFoundError,
    PaymentRequiredError,
    PaymentVerificationFailedError,
    TransactionAlreadyUsedError,
)
from app.domain.interfaces import ClientRepository, OriginProxy, PaymentVerifier
from app.domain.models import GatewayClient, PaymentInstructions, ProxyRequest, ProxyResponse

# Request headers passed through to the origin; everything else (cookies, X-Payment, hop-by-hop) is dropped.
FORWARD_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "authorization",
        "cache-control",
        "content-type",
        "user-agent",
    }
)


class GatewayService:
    def __init__(
        self,
        clients: ClientRepository,
        verifier: PaymentVerifier,
        proxy: OriginProxy,
        platform_wallet: str,
        usdc_contract: str,
        chain_id: int,
    ) -> None:
        self._clients = clients
        self._verifier = verifier
        self._proxy = proxy
        self._platform_wallet = platform_wallet
        self._usdc_contract = usdc_contract
        self._chain_id = chain_id

    async def get_payment_instructions(self, client_id: UUID) -> PaymentInstructions:
        client = await self._get_client(client_id)
        return self._instructions_for(client)

    async def handle_paid_request(self, client_id: UUID, tx_hash: str | None, request: ProxyRequest) -> ProxyResponse:
        client = await self._get_client(client_id)
        if not tx_hash:
            raise PaymentRequiredError(self._instructions_for(client))

        if await self._clients.is_transaction_used(tx_hash):
            raise TransactionAlreadyUsedError(tx_hash)

        verification = await self._verifier.verify(tx_hash, self._platform_wallet, client.price_per_request)
        if not verification.verified:
            raise PaymentVerificationFailedError(verification.error or "Payment not verified")

        await self._clients.record_payment(client.id, tx_hash, verification.amount)

        forwarded = ProxyRequest(
            headers={k: v for k, v in request.headers.items() if k.lower() in FORWARD_HEADERS},
            params=request.params,
            body=request.body or None,
        )
        return await self._proxy.forward(client.origin_url, forwarded)

    async def _get_client(self, client_id: UUID) -> GatewayClient:
        client = await self._clients.get_active_client(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client {client_id} not found or inactive")
        return client

    def _instructions_for(self, client: GatewayClient) -> PaymentInstructions:
        return PaymentInstructions(
            address=self._platform_wallet,
            amount=client.price_per_request,
            chain_id=self._chain_id,
            usdc_contract=self._usdc_contract,
        )
