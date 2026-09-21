"""Sentence-aware chunks with bounded word overlap within a single page and section."""

import math
import re
from dataclasses import dataclass

from app.ingestion.parser import SectionText


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    section_title: str | None
    chunk_index: int
    text: str
    token_count: int


def chunk_sections(
    sections: list[SectionText], size_tokens: int, overlap_tokens: int
) -> list[TextChunk]:
    """Estimate tokens as 4/3 words; split oversized sentences by words, never characters."""
    if size_tokens < 4 or not 0 <= overlap_tokens < size_tokens:
        raise ValueError("Chunk size must be >=4 and overlap must be in [0, size).")
    max_words = max(1, size_tokens * 3 // 4)
    overlap_words = min(overlap_tokens * 3 // 4, max_words - 1)
    chunks: list[TextChunk] = []
    for section in sections:
        buffer: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", section.text):
            words = sentence.split()
            while words:
                if buffer and len(buffer) + len(words) > max_words:
                    chunks.append(
                        TextChunk(
                            section.page_number,
                            section.section_title,
                            len(chunks),
                            " ".join(buffer),
                            math.ceil(len(buffer) * 4 / 3),
                        )
                    )
                    # Reduce overlap when necessary to fit a complete short sentence.
                    keep = (
                        overlap_words
                        if len(words) > max_words
                        else min(overlap_words, max_words - len(words))
                    )
                    buffer = buffer[-keep:] if keep else []
                capacity = max_words - len(buffer)
                buffer.extend(words[:capacity])
                words = words[capacity:]
        if buffer:
            chunks.append(
                TextChunk(
                    section.page_number,
                    section.section_title,
                    len(chunks),
                    " ".join(buffer),
                    math.ceil(len(buffer) * 4 / 3),
                )
            )
    return chunks
