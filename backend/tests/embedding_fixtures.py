"""Deterministic test vectors; these do not measure real model semantic quality."""

from collections.abc import Sequence

from app.retrieval.embeddings import EmbeddingSpec


class TestEmbedder:
    __test__ = False
    spec = EmbeddingSpec(key="test-fixture@v1", dimensions=3)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [0.0, 1.0, 0.0]
            if "battery" in text.lower()
            else [0.0, 0.0, 1.0]
            if "ocean" in text.lower()
            else [1.0, 0.0, 0.0]
            for text in texts
        ]
