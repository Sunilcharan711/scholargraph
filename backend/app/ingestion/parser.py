"""Conservative text extraction. No OCR or claims of perfect scientific layout parsing."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.core.errors import IngestionError

KNOWN_HEADING = re.compile(
    r"^(abstract|introduction|background|related work|methods?|methodology|"
    r"materials and methods|experiments?|results?|discussion|conclusions?|"
    r"limitations?|future work|references|acknowledg(?:e)?ments?)\s*[:.]?$",
    re.IGNORECASE,
)
NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+[A-Z][^.!?]{1,100}$")


@dataclass(frozen=True)
class SectionText:
    page_number: int
    section_title: str | None
    text: str


@dataclass(frozen=True)
class ParsedPaper:
    title: str
    authors: list[str]
    abstract: str | None
    page_count: int
    sections: list[SectionText]
    warnings: list[str]

    @property
    def full_text(self) -> str:
        return "\n\n".join(section.text for section in self.sections)


def is_heading(text: str) -> bool:
    return len(text) <= 120 and bool(
        KNOWN_HEADING.fullmatch(text) or NUMBERED_HEADING.fullmatch(text)
    )


def parse_pdf(path: Path, fallback_title: str, max_pages: int, max_chars: int) -> ParsedPaper:
    try:
        # Close the filesystem handle before entering native parsing. A failed native
        # open can retain a handle on Windows and prevent rejection cleanup.
        with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as document:
            if not document.is_pdf:
                raise IngestionError("The uploaded document is not a PDF.", 415)
            if document.needs_pass:
                raise IngestionError("Password-protected PDFs are not supported.")
            if not 0 < len(document) <= max_pages:
                raise IngestionError(f"PDF must contain between 1 and {max_pages} pages.", 413)
            metadata = document.metadata or {}
            title = str(metadata.get("title") or "").strip()
            authors = [a.strip() for a in re.split(r";", metadata.get("author") or "") if a.strip()]
            sections: list[SectionText] = []
            heading: str | None = None
            extracted = 0
            blank_pages = 0
            for number, page in enumerate(document, start=1):
                blocks = page.get_text(
                    "dict",
                    sort=True,
                    flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES,
                )["blocks"]
                paragraphs: list[str] = []
                title_candidates: list[tuple[float, str]] = []
                page_has_text = False
                for block in blocks:
                    lines: list[str] = []
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        text = " ".join(span["text"] for span in spans).strip()
                        extracted += len(text)
                        if extracted > max_chars:
                            raise IngestionError("PDF contains too much extracted text.", 413)
                        if not text:
                            continue
                        page_has_text = True
                        if number == 1 and len(text) <= 300 and not is_heading(text):
                            title_candidates.append((max(s["size"] for s in spans), text))
                        if is_heading(text):
                            if lines:
                                paragraphs.append(" ".join(lines))
                                lines = []
                            if paragraphs:
                                sections.append(
                                    SectionText(number, heading, "\n\n".join(paragraphs))
                                )
                                paragraphs = []
                            heading = text
                        else:
                            lines.append(text)
                    if lines:
                        paragraphs.append(" ".join(lines))
                if number == 1 and not title and title_candidates:
                    # Largest first-page line; ties prefer the earliest line.
                    title = max(title_candidates, key=lambda candidate: candidate[0])[1]
                if paragraphs:
                    sections.append(SectionText(number, heading, "\n\n".join(paragraphs)))
                if not page_has_text:
                    blank_pages += 1
            if not sections:
                raise IngestionError("PDF has no extractable text. Scanned PDFs require OCR.")
            abstract = (
                "\n\n".join(
                    section.text
                    for section in sections
                    if section.section_title
                    and re.fullmatch(
                        r"(?:\d+[.)]?\s+)?abstract\s*[:.]?", section.section_title, re.IGNORECASE
                    )
                )
                or None
            )
            warnings = ["Metadata and headings are heuristic; reading order may be imperfect."]
            if blank_pages:
                warnings.append(f"{blank_pages} page(s) have no extractable text; no OCR was run.")
            return ParsedPaper(
                title=title or fallback_title,
                authors=authors,
                abstract=abstract,
                page_count=len(document),
                sections=sections,
                warnings=warnings,
            )
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, RuntimeError) as exc:
        raise IngestionError("PDF is malformed or cannot be read.") from exc
