import math
import os
from collections.abc import Sequence
from pathlib import Path

import pymupdf
import pytest
from embedding_fixtures import TestEmbedder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.retrieval.embeddings import EmbeddingError, embed_texts, normalize_vector
from app.retrieval.sentence_transformer import SentenceTransformerEmbedder, text_windows


@pytest.mark.parametrize("vector", [[0, 0, 0], [1, 0], [float("nan"), 1, 0], [float("inf"), 0, 0]])
def test_invalid_vectors_rejected(vector: list[float]) -> None:
    with pytest.raises(ValueError):
        normalize_vector(vector, 3)


def test_normalization_and_output_count() -> None:
    assert normalize_vector([3, 4, 0], 3) == [0.6, 0.8, 0.0]

    class MissingVector(TestEmbedder):
        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            return []

    with pytest.raises(EmbeddingError, match="generation failed"):
        embed_texts(MissingVector(), ["nonempty"])


def test_windowing_covers_tail_without_exceeding_model_budget() -> None:
    text = " ".join(f"word{i}" for i in range(150))
    windows = text_windows(text, lambda value: len(value.split()) + 2, 32)
    assert len(windows) > 1
    assert " ".join(windows).split() == text.split()
    assert all(len(window.split()) + 2 <= 32 for window in windows)
    # Unbroken words are split only when necessary for model safety.
    assert "".join(text_windows("x" * 50, len, 10)) == "x" * 50


def test_windowing_rejects_empty_and_pathological_inputs() -> None:
    with pytest.raises(EmbeddingError):
        text_windows(" ", len, 32)
    with pytest.raises(EmbeddingError, match="too many"):
        text_windows("x" * 10000, len, 1)


def test_model_is_lazy_and_missing_offline_cache_is_clear(tmp_path: Path) -> None:
    provider = SentenceTransformerEmbedder(
        Settings(
            _env_file=None,
            embedding_cache_dir=tmp_path,
            embedding_local_files_only=True,
        )
    )
    assert provider._model is None
    assert provider.encode([]) == []
    with pytest.raises(EmbeddingError, match="model unavailable"):
        _ = provider.spec


@pytest.mark.model
def test_real_model_vectors_and_window_pooling() -> None:
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 to verify real model weights.")
    provider = SentenceTransformerEmbedder(Settings())
    text = "Photovoltaic panels produce electrical energy from sunlight. " * 80
    mixed = (
        "Photovoltaic panels produce electrical energy from sunlight. " * 40
        + "Vaccines train the immune system to protect against infectious disease. " * 80
    )
    vectors = embed_texts(provider, [text, "Solar cells generate electricity.", mixed])
    assert provider.spec.dimensions == 384  # This opt-in check targets the default MiniLM model.
    assert all(math.isclose(sum(value * value for value in v), 1.0, rel_tol=1e-5) for v in vectors)
    assert sum(a * b for a, b in zip(vectors[0], vectors[1], strict=True)) > 0.5
    # Both long texts start with solar content beyond the model limit. Later vaccine
    # content must affect the vector; truncating both to their prefixes would hide it.
    assert sum(a * b for a, b in zip(vectors[0], vectors[2], strict=True)) < 0.95


@pytest.mark.model
def test_real_model_upload_and_semantic_search(
    config: Settings,
    session_factory: sessionmaker[Session],
    pdf_bytes: bytes,
) -> None:
    if os.environ.get("RUN_MODEL_TESTS") != "1":
        pytest.skip("Set RUN_MODEL_TESTS=1 to verify real model weights.")
    provider = SentenceTransformerEmbedder(Settings())
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 60), "Battery storage experiment", fontsize=18)
        page.insert_text((72, 100), "Lithium-ion batteries store energy.")
        page.insert_text((72, 130), "Charging rate affects cell lifetime and capacity.")
        battery_pdf = document.tobytes()
    with TestClient(create_app(config, session_factory, provider)) as client:
        baseline = client.post("/api/papers/upload", files={"file": ("retrieval.pdf", pdf_bytes)})
        assert baseline.status_code == 201, baseline.text
        battery = client.post("/api/papers/upload", files={"file": ("battery.pdf", battery_pdf)})
        assert battery.status_code == 201, battery.text
        result = client.post(
            "/api/search",
            json={
                "query": "Which study discusses lithium ion cell charging and energy storage?",
                "top_k": 1,
            },
        )
        assert result.status_code == 200, result.text
        assert result.json()["results"][0]["paper_id"] == battery.json()["id"]
        assert result.json()["excluded_chunk_count"] == 0
        assert result.json()["embedding_dimensions"] == 384
        for mode in ("bm25", "hybrid"):
            result = client.post(
                "/api/search",
                json={
                    "query": "lithium ion charging",
                    "mode": mode,
                    "top_k": 1,
                    "diagnostics": True,
                },
            )
            assert result.status_code == 200, result.text
            assert result.json()["results"][0]["paper_id"] == battery.json()["id"]
