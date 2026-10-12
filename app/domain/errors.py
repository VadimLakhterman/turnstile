"""Domain errors. Translated to HTTP responses in app/core/errors.py."""

from app.domain.models import PaymentInstructions


class DomainError(Exception):
    """Base class for all business errors."""


class ClientNotFoundError(DomainError):
    pass


class PaymentRequiredError(DomainError):
    def __init__(self, instructions: PaymentInstructions) -> None:
        super().__init__("Payment required")
        self.instructions = instructions


class TransactionAlreadyUsedError(DomainError):
    def __init__(self, tx_hash: str) -> None:
        super().__init__(f"Transaction already used: {tx_hash}")
        self.tx_hash = tx_hash


class PaymentVerificationFailedError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PaymentVerifierUnavailableError(DomainError):
    """The payment verification backend (e.g. RPC node) could not be reached."""


class LedgerWriteError(DomainError):
    """A verified payment could not be recorded."""


class UpstreamUnavailableError(DomainError):
    """The client's origin API could not be reached."""
