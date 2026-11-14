"""Persisted graph snapshots and measured evaluation runs."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.paper import json_type


class PaperRelationship(Base):
    __tablename__ = "paper_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_paper_id", "target_paper_id", "relationship_type", name="uq_relationship_pair"
        ),
        CheckConstraint("source_paper_id <> target_paper_id", name="ck_relationship_distinct"),
        CheckConstraint(
            "similarity_score >= -1 AND similarity_score <= 1", name="ck_relationship_score"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_paper_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    target_paper_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(40), default="semantic_similarity")
    similarity_score: Mapped[float] = mapped_column(Float)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    report: Mapped[dict[str, Any]] = mapped_column(json_type)
