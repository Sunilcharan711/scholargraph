"""Synchronous ingestion with compensating cleanup on parsing or transaction failure."""

import logging
from dataclasses import asdict
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import IngestionError
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_pdf
from app.ingestion.storage import save_pdf, stored_path, validate_filename
from app.models import Paper, PaperChunk
from app.retrieval.embeddings import EmbeddingProvider
from app.services.indexing import assign_embeddings

logger = logging.getLogger(__name__)


def ingest_paper(
    upload: UploadFile, session: Session, config: Settings, embedder: EmbeddingProvider
) -> Paper:
    filename = validate_filename(upload.filename, upload.content_type)
    basename, byte_count = save_pdf(
        upload.file, config.upload_dir, config.max_file_size_mb * 1024 * 1024
    )
    path = stored_path(config.upload_dir, basename)
    try:
        parsed = parse_pdf(path, filename[:-4], config.max_pdf_pages, config.max_extracted_chars)
        chunks = chunk_sections(
            parsed.sections, config.chunk_size_tokens, config.chunk_overlap_tokens
        )
        paper = Paper(
            title=parsed.title,
            authors=parsed.authors,
            abstract=parsed.abstract,
            filename=filename,
            file_path=basename,
            processing_status="ready",
            metadata_json={
                "page_count": parsed.page_count,
                "byte_count": byte_count,
                "chunk_count": len(chunks),
                "sections": list(
                    dict.fromkeys(
                        section.section_title
                        for section in parsed.sections
                        if section.section_title
                    )
                ),
                "warnings": parsed.warnings,
                "parser": "pymupdf",
                "chunk_size_tokens": config.chunk_size_tokens,
                "chunk_overlap_tokens": config.chunk_overlap_tokens,
                "token_estimator": "ceil(word_count * 4 / 3)",
            },
        )
        paper.chunks = [PaperChunk(**asdict(chunk)) for chunk in chunks]
        assign_embeddings(paper, paper.chunks, embedder)
        session.add(paper)
        session.flush()
        # Load server-generated fields before commit; no post-commit query can trigger cleanup.
        session.refresh(paper)
        session.commit()
        return paper
    except Exception:
        session.rollback()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.error("Could not remove failed ingestion file %s", basename)
        raise


def delete_paper(paper_id: UUID, session: Session, config: Settings) -> bool:
    paper = session.scalar(select(Paper).where(Paper.id == paper_id).with_for_update())
    if paper is None:
        return False
    path = stored_path(config.upload_dir, paper.file_path)
    # Persist intent before touching the filesystem. A failed unlink or final commit
    # leaves a retryable 'deleting' record rather than an invisible orphaned PDF.
    paper.processing_status = "deleting"
    session.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise IngestionError("Could not remove stored PDF. Retry deletion later.", 503) from exc
    session.delete(paper)
    session.commit()
    return True
