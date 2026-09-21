"""Paper provenance and chunks with versioned, dimension-tagged embeddings."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

json_type = JSON().with_variant(JSONB(), "postgresql")


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint("processing_status IN ('ready', 'deleting')", name="ck_paper_status"),
        Index("ix_papers_uploaded_at_id", "uploaded_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(json_type, default=list)
    abstract: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(200))
    # Relative generated basename, never an arbitrary client-provided path.
    file_path: Mapped[str] = mapped_column(String(100), unique=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict)
    chunks: Mapped[list["PaperChunk"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", passive_deletes=True
    )


class PaperChunk(Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("paper_id", "chunk_index", name="uq_chunk_paper_index"),
        CheckConstraint("page_number > 0", name="ck_chunk_page_positive"),
        CheckConstraint("chunk_index >= 0", name="ck_chunk_index_nonnegative"),
        CheckConstraint("token_count > 0", name="ck_chunk_tokens_positive"),
        Index("ix_chunks_paper_page", "paper_id", "page_number"),
        Index("ix_chunks_embedding_space", "embedding_model", "embedding_dimensions"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND "
            "embedding_dimensions IS NOT NULL AND embedding_dimensions > 0)",
            name="ck_chunk_embedding_metadata",
        ),
        CheckConstraint(
            "embedding IS NULL OR vector_dims(embedding) = embedding_dimensions",
            name="ck_chunk_vector_dimensions",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    # A dimensionless column permits deliberate model changes; search filters the space.
    # JSON is strictly a SQLite test variant, not a production retrieval backend.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector().with_variant(JSON(none_as_null=True), "sqlite")
    )
    embedding_model: Mapped[str | None] = mapped_column(String(512))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paper: Mapped[Paper] = relationship(back_populates="chunks")
