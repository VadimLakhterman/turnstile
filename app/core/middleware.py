from contextvars import ContextVar
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Request-ID"
MAX_INBOUND_ID_LENGTH = 128

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationIdMiddleware:
    """Reuse the caller's X-Request-ID (or mint one), expose it to logs and handlers, echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = Headers(scope=scope).get(CORRELATION_HEADER)
        correlation_id = inbound if inbound and len(inbound) <= MAX_INBOUND_ID_LENGTH else uuid4().hex
        # Stored on the shared scope so the outermost 500 handler can still read it.
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        token = correlation_id_var.set(correlation_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault(CORRELATION_HEADER, correlation_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", None) or correlation_id_var.get()
