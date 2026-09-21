"""Lazy local inference with pinned snapshot identity and full-text window pooling."""

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.retrieval.embeddings import EmbeddingError, EmbeddingSpec, normalize_vector

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def text_windows(text: str, token_count: Callable[[str], int], limit: int) -> list[str]:
    """Recursively split oversized inputs at whitespace; preserve every non-space character.

    Counts include special tokens. A long unbroken word can be split as a last resort.
    This is model-input windowing, not a replacement for the provenance-aware chunker.
    """
    pending = [text.strip()]
    windows: list[str] = []
    while pending:
        part = pending.pop()
        if not part:
            raise EmbeddingError("Cannot embed empty text.", 422)
        if token_count(part) <= limit:
            windows.append(part)
            continue
        if len(part) < 2 or len(pending) + len(windows) >= 127:
            raise EmbeddingError("Text requires too many model input windows.", 422)
        midpoint = len(part) // 2
        split = part.rfind(" ", len(part) // 4, midpoint + 1)
        if split <= 0:
            split = midpoint
        left, right = part[:split].strip(), part[split:].strip()
        pending.extend([right, left])
    return windows


class SentenceTransformerEmbedder:
    """One cached CPU model per application process; no remote document API calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: SentenceTransformer | None = None
        self._spec: EmbeddingSpec | None = None
        self._lock = RLock()

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from huggingface_hub import snapshot_download
            from sentence_transformers import SentenceTransformer

            snapshot = snapshot_download(
                repo_id=self.settings.embedding_model,
                revision=self.settings.embedding_revision,
                cache_dir=str(self.settings.embedding_cache_dir),
                local_files_only=self.settings.embedding_local_files_only,
                max_workers=1,
                allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.vocab"],
            )
            model = SentenceTransformer(
                snapshot,
                device=self.settings.embedding_device,
                trust_remote_code=False,
                local_files_only=True,
                model_kwargs={"use_safetensors": True},
            )
            dimension_method = getattr(model, "get_embedding_dimension", None)
            dimensions = (
                dimension_method()
                if dimension_method is not None
                else model.get_sentence_embedding_dimension()
            )
            if dimensions is None or not 1 <= dimensions <= 16000:
                raise ValueError("Unsupported model embedding dimensions")
            if not isinstance(model.max_seq_length, int) or model.max_seq_length < 8:
                raise ValueError("A text model with a bounded input length is required")
            self._spec = EmbeddingSpec(
                key=f"{self.settings.embedding_model}@{Path(snapshot).name}:window-mean-v1",
                dimensions=dimensions,
            )
            self._model = model
        except Exception as exc:
            logger.error("Embedding model could not load (%s)", type(exc).__name__)
            raise EmbeddingError(
                "Embedding model unavailable. Check model settings, cache, and download access."
            ) from exc

    @property
    def spec(self) -> EmbeddingSpec:
        with self._lock:
            self._load()
            assert self._spec is not None
            return self._spec

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._lock:
            self._load()
            assert self._model is not None and self._spec is not None
            model = self._model

            def count(text: str) -> int:
                return len(
                    model.tokenizer.encode(
                        text,
                        add_special_tokens=True,
                        truncation=False,
                        verbose=False,
                    )
                )

            windows: list[str] = []
            groups: list[tuple[int, int]] = []
            for text in texts:
                parts = text_windows(text, count, model.max_seq_length)
                groups.append((len(windows), len(windows) + len(parts)))
                windows.extend(parts)
            vectors = model.encode(
                windows,
                batch_size=self.settings.embedding_batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                prompt="",
            )
            special_tokens = model.tokenizer.num_special_tokens_to_add(pair=False)
            result: list[list[float]] = []
            for start, end in groups:
                weights = [max(1, count(window) - special_tokens) for window in windows[start:end]]
                pooled = sum(
                    vector * weight
                    for vector, weight in zip(vectors[start:end], weights, strict=True)
                ) / sum(weights)
                result.append(normalize_vector(pooled.tolist(), self._spec.dimensions))
            return result
