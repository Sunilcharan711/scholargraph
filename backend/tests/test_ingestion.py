from io import BytesIO
from pathlib import Path
from uuid import UUID

import pymupdf
import pytest

from app.core.errors import IngestionError
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import SectionText, parse_pdf
from app.ingestion.storage import save_pdf, stored_path, validate_filename


@pytest.mark.parametrize(
    "name,mime",
    [
        ("paper.txt", "application/pdf"),
        ("paper.pdf", "text/plain"),
        (None, "application/pdf"),
        ("paper.pdf.exe", "application/pdf"),
    ],
)
def test_invalid_upload_metadata(name: str | None, mime: str) -> None:
    with pytest.raises(IngestionError):
        validate_filename(name, mime)


def test_filename_sanitization() -> None:
    assert validate_filename("../../a?.PDF", "application/pdf") == "a_.pdf"
    assert validate_filename("C:\\private\\study.pdf", None) == "study.pdf"


def test_storage_limits_and_collision_avoidance(tmp_path: Path, pdf_bytes: bytes) -> None:
    first, size = save_pdf(BytesIO(pdf_bytes), tmp_path, len(pdf_bytes))
    second, _ = save_pdf(BytesIO(pdf_bytes), tmp_path, len(pdf_bytes))
    assert first != second
    assert size == len(pdf_bytes)
    assert stored_path(tmp_path, first).read_bytes() == pdf_bytes
    with pytest.raises(IngestionError, match="exceeds"):
        save_pdf(BytesIO(pdf_bytes), tmp_path, 10)
    assert len(list(tmp_path.iterdir())) == 2


def test_storage_collision_never_removes_existing_file(
    tmp_path: Path,
    pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_id = UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr("app.ingestion.storage.uuid4", lambda: fixed_id)
    basename, _ = save_pdf(BytesIO(pdf_bytes), tmp_path, len(pdf_bytes))
    with pytest.raises(FileExistsError):
        save_pdf(BytesIO(pdf_bytes), tmp_path, len(pdf_bytes))
    assert (tmp_path / basename).read_bytes() == pdf_bytes


@pytest.mark.parametrize("name", ["../secret.pdf", "C:/secret.pdf", "paper.pdf"])
def test_stored_paths_reject_traversal(tmp_path: Path, name: str) -> None:
    with pytest.raises(IngestionError):
        stored_path(tmp_path, name)


def test_invalid_signature_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="signature"):
        save_pdf(BytesIO(b"pretend PDF"), tmp_path, 100)
    assert not list(tmp_path.iterdir())


def test_parser_extracts_provenance(tmp_path: Path, pdf_bytes: bytes) -> None:
    path = tmp_path / "test.pdf"
    path.write_bytes(pdf_bytes)
    parsed = parse_pdf(path, "fallback", 10, 10000)
    assert parsed.title == "A Small Research Study"
    assert parsed.authors == ["Ada Example", "Lee Example"]
    assert parsed.abstract and "reliable research retrieval" in parsed.abstract
    assert parsed.page_count == 2
    assert any(s.page_number == 2 and s.section_title == "2 Methods" for s in parsed.sections)
    assert "tiny synthetic dataset" in parsed.full_text
    with pytest.raises(IngestionError, match="pages"):
        parse_pdf(path, "fallback", 1, 10000)
    with pytest.raises(IngestionError, match="too much"):
        parse_pdf(path, "fallback", 10, 10)


def test_parser_fallback_and_rejections(tmp_path: Path) -> None:
    path = tmp_path / "test.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a real PDF")
    with pytest.raises(IngestionError, match="malformed"):
        parse_pdf(path, "fallback", 10, 10000)
    with pymupdf.open() as document:
        page = document.new_page()
        document.save(path)
        with pytest.raises(IngestionError, match="OCR"):
            parse_pdf(path, "fallback", 10, 10000)
        page.insert_text((72, 60), "A Useful Title", fontsize=20)
        page.insert_text((72, 100), "A short paragraph of original research text.")
        document.save(path)
        assert parse_pdf(path, "fallback", 10, 10000).title == "A Useful Title"
        document.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="password")
        with pytest.raises(IngestionError, match="Password"):
            parse_pdf(path, "fallback", 10, 10000)


def test_chunker_preserves_boundaries_and_words() -> None:
    text = " ".join(f"word{i}" for i in range(100))
    sections = [SectionText(1, "Methods", text), SectionText(2, "Results", "A short result.")]
    chunks = chunk_sections(sections, 32, 8)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(0 < c.token_count <= 32 for c in chunks)
    assert chunks[-1].page_number == 2 and chunks[-1].section_title == "Results"
    assert set(text.split()) == {word for c in chunks[:-1] for word in c.text.split()}
    assert chunks[0].text.split()[-6:] == chunks[1].text.split()[:6]


def test_sentence_boundaries_and_empty_input() -> None:
    sections = [SectionText(1, "Abstract", "One short sentence. Another short sentence.")]
    chunks = chunk_sections(sections, 6, 0)
    assert [c.text for c in chunks] == ["One short sentence.", "Another short sentence."]
    assert chunk_sections([], 32, 0) == []
    with pytest.raises(ValueError):
        chunk_sections(sections, 32, 32)
