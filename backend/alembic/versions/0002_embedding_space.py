"""Tag vectors with their model revision and dimensions; legacy chunks stay unindexed."""

import sqlalchemy as sa

from alembic import op

revision = "0002_embedding_space"
down_revision = "0001_papers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Milestone 1 wrote only NULL vectors. Refuse an unexpected populated column;
    # guessing its model would mix vector spaces or discard user data.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM paper_chunks WHERE embedding IS NOT NULL) THEN
                RAISE EXCEPTION 'Unversioned vectors exist; label or back up them before migrating';
            END IF;
        END $$;
    """)
    op.add_column("paper_chunks", sa.Column("embedding_model", sa.String(512)))
    op.add_column("paper_chunks", sa.Column("embedding_dimensions", sa.Integer()))
    op.create_check_constraint(
        "ck_chunk_embedding_metadata",
        "paper_chunks",
        "(embedding IS NULL AND embedding_model IS NULL AND embedding_dimensions IS NULL) OR "
        "(embedding IS NOT NULL AND embedding_model IS NOT NULL AND "
        "embedding_dimensions IS NOT NULL AND embedding_dimensions > 0)",
    )
    op.create_index(
        "ix_chunks_embedding_space", "paper_chunks", ["embedding_model", "embedding_dimensions"]
    )
    op.create_check_constraint(
        "ck_chunk_vector_dimensions",
        "paper_chunks",
        "embedding IS NULL OR vector_dims(embedding) = embedding_dimensions",
    )


def downgrade() -> None:
    # Removing version metadata would leave unsafe unlabelled vectors; back up first.
    op.execute(
        "UPDATE paper_chunks SET embedding = NULL, embedding_model = NULL, "
        "embedding_dimensions = NULL"
    )
    op.drop_constraint("ck_chunk_vector_dimensions", "paper_chunks", type_="check")
    op.drop_index("ix_chunks_embedding_space", table_name="paper_chunks")
    op.drop_constraint("ck_chunk_embedding_metadata", "paper_chunks", type_="check")
    op.drop_column("paper_chunks", "embedding_dimensions")
    op.drop_column("paper_chunks", "embedding_model")
