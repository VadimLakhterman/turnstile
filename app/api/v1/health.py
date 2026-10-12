from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")
