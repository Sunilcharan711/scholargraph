"""Process liveness endpoint; does not assert database or provider readiness."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report whether the API process can serve requests."""
    return HealthResponse()


@router.get("/status", tags=["health"])
def status(request: Request) -> dict:
    config = request.app.state.settings
    return {
        "storage": request.app.state.storage_mode,
        "answer_model": config.chat_model or None,
        "answer_provider": config.llm_provider or None,
    }
