"""Paper relationships and evaluation reports."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_research"
down_revision = "0002_embedding_space"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_paper_id",
            sa.Uuid(),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_paper_id",
            sa.Uuid(),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.UniqueConstraint(
            "source_paper_id", "target_paper_id", "relationship_type", name="uq_relationship_pair"
        ),
        sa.CheckConstraint("source_paper_id <> target_paper_id", name="ck_relationship_distinct"),
        sa.CheckConstraint(
            "similarity_score >= -1 AND similarity_score <= 1", name="ck_relationship_score"
        ),
    )
    for column in ("source_paper_id", "target_paper_id"):
        op.create_index(f"ix_paper_relationships_{column}", "paper_relationships", [column])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("report", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("paper_relationships")
