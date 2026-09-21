"""Provider contract and validation shared by ingestion, backfill, and search."""

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """A safe error message, never an upstream exception containing paths or tokens."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EmbeddingSpec:
    key: str
    dimensions: int


class EmbeddingProvider(Protocol):
    @property
    def spec(self) -> EmbeddingSpec: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalize_vector(vector: Sequence[float], dimensions: int) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) != dimensions or not all(math.isfinite(value) for value in values):
        raise ValueError("Invalid vector shape or non-finite values")
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Vector must have a finite nonzero norm")
    return [value / norm for value in values]


def embed_texts(provider: EmbeddingProvider, texts: Sequence[str]) -> list[list[float]]:
    """Enforce one finite, normalized, nonzero vector per input before persistence."""
    if not texts:
        return []
    try:
        vectors = provider.encode(texts)
        if len(vectors) != len(texts):
            raise ValueError("Embedding output count differs from input count")
        return [normalize_vector(vector, provider.spec.dimensions) for vector in vectors]
    except EmbeddingError:
        raise
    except Exception as exc:
        logger.error("Embedding generation failed (%s)", type(exc).__name__)
        raise EmbeddingError("Embedding generation failed. Check the model configuration.") from exc
