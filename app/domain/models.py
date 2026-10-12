"""Business entities and value objects. Pure Python — no framework or SDK imports."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class GatewayClient:
    id: UUID
    origin_url: str
    price_per_request: Decimal


@dataclass(frozen=True)
class PaymentInstructions:
    address: str
    amount: Decimal
    chain_id: int
    usdc_contract: str
    currency: str = "USDC"
    network: str = "base"


@dataclass(frozen=True)
class PaymentVerification:
    verified: bool
    amount: Decimal
    error: str | None = None


@dataclass(frozen=True)
class ProxyRequest:
    headers: dict[str, str]
    params: dict[str, str]
    body: bytes | None


@dataclass(frozen=True)
class ProxyResponse:
    status_code: int
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)
