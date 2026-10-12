from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response

from app.api.v1.deps import GatewayServiceDep
from app.domain.models import ProxyRequest
from app.schemas.gateway import GatewayErrorResponse, PaymentRequiredResponse

router = APIRouter(prefix="/v1/gateway", tags=["gateway"])

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": GatewayErrorResponse} for status in (400, 404, 409, 500, 502)
}


@router.get("/{client_id}", responses=ERROR_RESPONSES)
async def gateway_info(client_id: UUID, service: GatewayServiceDep) -> PaymentRequiredResponse:
    """Return payment instructions for this client's gateway."""
    instructions = await service.get_payment_instructions(client_id)
    return PaymentRequiredResponse.from_instructions(instructions)


@router.post("/{client_id}", responses={402: {"model": PaymentRequiredResponse}, **ERROR_RESPONSES})
async def gateway(
    client_id: UUID,
    request: Request,
    service: GatewayServiceDep,
    x_payment: Annotated[str | None, Header(alias="X-Payment")] = None,
) -> Response:
    """Verify the payment in X-Payment and proxy the request to the client's origin."""
    proxy_request = ProxyRequest(
        headers=dict(request.headers),
        params=dict(request.query_params),
        body=await request.body(),
    )
    upstream = await service.handle_paid_request(client_id, x_payment, proxy_request)
    return Response(content=upstream.content, status_code=upstream.status_code, headers=upstream.headers)
