from pydantic import BaseModel

from app.domain.models import PaymentInstructions


class PaymentInfo(BaseModel):
    address: str
    amount: str
    currency: str
    network: str
    chain_id: int
    usdc_contract: str


class PaymentRequiredResponse(BaseModel):
    x402_version: int = 1
    payment: PaymentInfo

    @classmethod
    def from_instructions(cls, instructions: PaymentInstructions) -> "PaymentRequiredResponse":
        return cls(
            payment=PaymentInfo(
                address=instructions.address,
                amount=str(instructions.amount),
                currency=instructions.currency,
                network=instructions.network,
                chain_id=instructions.chain_id,
                usdc_contract=instructions.usdc_contract,
            )
        )


class GatewayErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    correlation_id: str | None = None
