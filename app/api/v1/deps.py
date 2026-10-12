from typing import Annotated

from fastapi import Depends

from app.core.provider import get_gateway_service
from app.domain.gateway_service import GatewayService

GatewayServiceDep = Annotated[GatewayService, Depends(get_gateway_service)]
