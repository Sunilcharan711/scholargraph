"""File validation and storage; only generated basenames address stored PDFs."""

import re
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.errors import IngestionError


def validate_filename(filename: str | None, content_type: str | None) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name.lower().endswith(".pdf"):
        raise IngestionError("Only .pdf files are accepted.", 415)
    if content_type and content_type.split(";", 1)[0].lower() not in {
        "application/pdf",
        "application/octet-stream",
    }:
        raise IngestionError("Content type must be application/pdf.", 415)
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", name[:-4]).strip(" .")[:180]
    return f"{safe or 'paper'}.pdf"


def stored_path(root: Path, basename: str) -> Path:
    """Reject traversal, absolute paths, unexpected names, and symlink escapes."""
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", basename):
        raise IngestionError("Stored file path is invalid; contact the administrator.", 409)
    resolved_root = root.resolve()
    target = resolved_root / basename
    if target.is_symlink() or target.resolve().parent != resolved_root:
        raise IngestionError("Stored file path is unsafe; contact the administrator.", 409)
    return target


def save_pdf(stream: BinaryIO, root: Path, max_bytes: int) -> tuple[str, int]:
    """Stream to an exclusive filename, enforcing actual bytes rather than headers."""
    header = stream.read(5)
    if header != b"%PDF-":
        raise IngestionError("The uploaded file does not have a valid PDF signature.", 415)
    root.mkdir(parents=True, exist_ok=True)
    basename = f"{uuid4().hex}.pdf"
    path = stored_path(root, basename)
    size = len(header)
    # Open outside the cleanup block: an exclusive-open collision must never
    # delete the pre-existing file that caused it.
    destination = path.open("xb")
    try:
        with destination:
            destination.write(header)
            while block := stream.read(64 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise IngestionError("PDF exceeds MAX_FILE_SIZE_MB.", 413)
                destination.write(block)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return basename, size
