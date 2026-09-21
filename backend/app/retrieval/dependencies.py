from typing import Annotated

from fastapi import Depends, Request

from app.retrieval.embeddings import EmbeddingProvider


def get_embedder(request: Request) -> EmbeddingProvider:
    return request.app.state.embedder


Embedder = Annotated[EmbeddingProvider, Depends(get_embedder)]
