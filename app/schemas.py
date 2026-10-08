from pydantic import BaseModel

from app.config import settings


class PaymentInfo(BaseModel):
    address: str
    amount: str
    currency: str = "USDC"
    network: str = "base"
    chain_id: int = settings.CHAIN_ID
    usdc_contract: str


class PaymentRequiredResponse(BaseModel):
    x402_version: int = 1
    payment: PaymentInfo


class GatewayErrorResponse(BaseModel):
    error: str
    detail: str | None = None
