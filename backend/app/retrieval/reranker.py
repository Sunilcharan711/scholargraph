"""Optional local cross-encoder scoring; bounded candidates and explicit failures."""

import logging
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Paper, PaperChunk
from app.retrieval.base import RetrievalHit

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    @property
    def identity(self) -> str: ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Lazy, serialized CPU inference using safetensors without remote model code."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._identity = ""
        self._lock = RLock()

    @property
    def identity(self) -> str:
        return self._identity

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        if len(passages) > 50:
            raise HTTPException(422, "Reranking supports at most 50 candidates.")
        if not self.settings.reranker_model:
            raise HTTPException(503, "Set RERANKER_MODEL before enabling reranking.")
        try:
            with self._lock:
                import torch
                from huggingface_hub import snapshot_download
                from sentence_transformers import CrossEncoder

                if self._model is None:
                    snapshot = snapshot_download(
                        repo_id=self.settings.reranker_model,
                        revision=self.settings.reranker_revision,
                        cache_dir=str(self.settings.embedding_cache_dir),
                        local_files_only=self.settings.reranker_local_files_only,
                        max_workers=1,
                        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.vocab"],
                    )
                    model = CrossEncoder(
                        snapshot,
                        device="cpu",
                        max_length=512,
                        trust_remote_code=False,
                        local_files_only=True,
                        model_kwargs={"use_safetensors": True},
                        activation_fn=torch.nn.Identity(),
                    )
                    if model.num_labels != 1:
                        raise ValueError("Reranker must output one relevance score per pair")
                    self._model = model
                    self._identity = (
                        f"{self.settings.reranker_model}@{Path(snapshot).name}:pair-512-logit-v1"
                    )
                scores = self._model.predict(
                    [(query, passage) for passage in passages],
                    batch_size=self.settings.reranker_batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    activation_fn=torch.nn.Identity(),
                )
                return [float(score) for score in scores]
        except Exception as exc:
            logger.error("Reranker unavailable (%s)", type(exc).__name__)
            raise HTTPException(
                503, "Reranker unavailable. Check model settings, cache, and download access."
            ) from exc


def rerank_hits(
    session: Session, query: str, hits: list[RetrievalHit], provider: Reranker
) -> list[RetrievalHit]:
    """Score authoritative chunk text and preserve provenance and first-stage scores."""
    if not hits:
        return []
    rows = session.execute(
        select(PaperChunk.id, PaperChunk.text)
        .join(Paper)
        .where(
            PaperChunk.id.in_([hit.chunk_id for hit in hits]), Paper.processing_status == "ready"
        )
    ).all()
    texts = dict(rows)
    candidates = [hit for hit in hits if hit.chunk_id in texts]
    if not candidates:
        return []
    scores = provider.score(query, [texts[hit.chunk_id] for hit in candidates])
    if len(scores) != len(candidates) or any(not math.isfinite(score) for score in scores):
        raise HTTPException(503, "Reranker returned invalid scores.")
    ranked = []
    for rank, (hit, score) in enumerate(zip(candidates, scores, strict=True), 1):
        diagnostics = hit.diagnostics.model_copy(
            update={
                "retrieval_rank": rank,
                "retrieval_score": hit.score,
                "reranker_score": score,
            }
        )
        ranked.append(replace(hit, score=score, diagnostics=diagnostics))
    return sorted(ranked, key=lambda hit: (-hit.score, hit.chunk_id))
