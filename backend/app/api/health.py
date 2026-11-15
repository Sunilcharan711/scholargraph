"""Process liveness endpoint; does not assert database or provider readiness."""

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.db.session import AppSettings, DatabaseSession
from app.models import Paper

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


@router.get("/ready", tags=["health"])
def readiness(session: DatabaseSession, config: AppSettings) -> dict:
    """Check the database schema and configured model inventory without generating."""
    session.execute(select(Paper.id).limit(1))
    if not config.llm_provider and not config.chat_model:
        return {"status": "ok", "database": "ok", "answer_model": "disabled"}
    if config.llm_provider != "ollama" or not config.chat_model:
        raise HTTPException(503, "Answer model configuration is incomplete.")
    try:
        with httpx.Client(timeout=httpx.Timeout(3, connect=2), trust_env=False) as client:
            response = client.get(config.ollama_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            inventory = response.json()["models"]
            names = {item["name"] for item in inventory}
            expected = config.chat_model
            if expected not in names and (":" in expected or expected + ":latest" not in names):
                raise ValueError("Missing configured model")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Configured answer model is unavailable.") from exc
    return {"status": "ok", "database": "ok", "answer_model": "available"}
