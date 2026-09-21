"""Enable pgvector and create paper provenance and chunk tables."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_papers"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.create_table(
        "papers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(), nullable=False),
        sa.Column("abstract", sa.Text()),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("file_path", sa.String(100), nullable=False, unique=True),
        sa.Column("source_url", sa.Text()),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processing_status", sa.String(20), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("processing_status IN ('ready', 'deleting')", name="ck_paper_status"),
    )
    op.create_index("ix_papers_uploaded_at_id", "papers", ["uploaded_at", "id"])
    op.create_index("ix_papers_processing_status", "papers", ["processing_status"])
    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "paper_id", sa.Uuid(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.Text()),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("paper_id", "chunk_index", name="uq_chunk_paper_index"),
        sa.CheckConstraint("page_number > 0", name="ck_chunk_page_positive"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunk_index_nonnegative"),
        sa.CheckConstraint("token_count > 0", name="ck_chunk_tokens_positive"),
    )
    op.create_index("ix_chunks_paper_page", "paper_chunks", ["paper_id", "page_number"])


def downgrade() -> None:
    op.drop_table("paper_chunks")
    op.drop_table("papers")
    # Leave the shared vector extension installed; other schemas may depend on it.
