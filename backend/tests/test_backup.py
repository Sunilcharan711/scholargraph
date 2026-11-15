import io
import tarfile
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../escape.pdf", "file"),
        ("/absolute.pdf", "file"),
        ("a" * 32 + ".pdf", "symlink"),
        ("a" * 32 + ".pdf", "duplicate"),
    ],
)
def test_backup_archive_rejects_unsafe_members(tmp_path, monkeypatch, name, kind):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from manage_backup import validate_archive

    path = tmp_path / "uploads.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo(name)
        if kind == "symlink":
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc/passwd"
        archive.addfile(item, io.BytesIO())
        if kind == "duplicate":
            archive.addfile(item, io.BytesIO())
    with pytest.raises(ValueError, match="Unsafe"):
        validate_archive(path)


def test_backup_archive_accepts_flat_generated_pdf_names(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    from manage_backup import validate_archive

    path = tmp_path / "uploads.tar.gz"
    name = "b" * 32 + ".pdf"
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(tarfile.TarInfo(name), io.BytesIO())
    assert validate_archive(path) == {name}
