from __future__ import annotations

from fastapi import APIRouter

from atm10_helper.api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")