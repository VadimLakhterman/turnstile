"""The single place where errors are logged and translated to HTTP responses."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.middleware import CORRELATION_HEADER, get_correlation_id
from app.domain.errors import (
    ClientNotFoundError,
    DomainError,
    LedgerWriteError,
    PaymentRequiredError,
    PaymentVerificationFailedError,
    PaymentVerifierUnavailableError,
    TransactionAlreadyUsedError,
    UpstreamUnavailableError,
)
from app.schemas.gateway import GatewayErrorResponse, PaymentRequiredResponse

logger = logging.getLogger(__name__)

# Domain error -> (HTTP status, client-facing message). Internal messages never reach the client.
ERROR_RESPONSES: dict[type[DomainError], tuple[int, str]] = {
    ClientNotFoundError: (404, "Client not found"),
    TransactionAlreadyUsedError: (409, "Transaction already used"),
    PaymentVerificationFailedError: (400, "Payment verification failed"),
    PaymentVerifierUnavailableError: (502, "Payment verification temporarily unavailable"),
    LedgerWriteError: (500, "Internal error recording payment"),
    UpstreamUnavailableError: (502, "Upstream service unavailable"),
}


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = get_correlation_id(request)

    if isinstance(exc, PaymentRequiredError):
        body = PaymentRequiredResponse.from_instructions(exc.instructions)
        return JSONResponse(status_code=402, content=body.model_dump())

    status_code, message = next(
        (resp for err_type, resp in ERROR_RESPONSES.items() if isinstance(exc, err_type)),
        (500, "Internal server error"),
    )
    detail: str | None = None
    if isinstance(exc, TransactionAlreadyUsedError):
        detail = exc.tx_hash
    elif isinstance(exc, PaymentVerificationFailedError):
        detail = exc.reason

    if status_code >= 500:
        logger.error("%s: %s", type(exc).__name__, exc, exc_info=exc, extra={"correlation_id": correlation_id})
    else:
        logger.info("%s: %s", type(exc).__name__, exc, extra={"correlation_id": correlation_id})

    body_err = GatewayErrorResponse(error=message, detail=detail, correlation_id=correlation_id)
    return JSONResponse(status_code=status_code, content=body_err.model_dump())


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = get_correlation_id(request)
    logger.error("Unhandled error: %s", exc, exc_info=exc, extra={"correlation_id": correlation_id})
    body = GatewayErrorResponse(error="Internal server error", correlation_id=correlation_id)
    # Runs outside the correlation middleware, so set the header here.
    return JSONResponse(status_code=500, content=body.model_dump(), headers={CORRELATION_HEADER: correlation_id})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
