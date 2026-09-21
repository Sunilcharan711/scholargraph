from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.models import Paper, PaperChunk


def test_upload_list_detail_delete(
    client: TestClient, pdf_bytes: bytes, config: Settings, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        "/api/papers/upload", files={"file": ("../../study.pdf", pdf_bytes, "application/pdf")}
    )
    assert response.status_code == 201, response.text
    paper = response.json()
    assert paper["filename"] == "study.pdf"
    assert paper["processing_status"] == "ready"
    assert "file_path" not in paper
    paper_id = paper["id"]
    assert client.get("/api/papers").json()["total"] == 1
    assert client.get("/api/papers?offset=1").json()["items"] == []
    detail = client.get(f"/api/papers/{paper_id}?chunk_limit=1").json()
    assert detail["chunk_count"] >= 3
    assert len(detail["chunks"]) == 1
    assert detail["chunks"][0]["page_number"] == 1
    assert len(list(config.upload_dir.iterdir())) == 1
    with session_factory() as session:
        chunks = list(session.scalars(select(PaperChunk)))
        assert chunks and all(c.embedding is not None for c in chunks)
        assert all(c.embedding_model == "test-fixture@v1" for c in chunks)
    assert client.delete(f"/api/papers/{paper_id}").status_code == 204
    assert client.get(f"/api/papers/{paper_id}").status_code == 404
    assert client.delete(f"/api/papers/{paper_id}").status_code == 404
    assert not list(config.upload_dir.iterdir())
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaperChunk)) == 0


@pytest.mark.parametrize(
    "filename,mime,payload,code",
    [
        ("x.txt", "application/pdf", b"abc", 415),
        ("x.pdf", "text/plain", b"abc", 415),
        ("x.pdf", "application/pdf", b"abc", 415),
        ("x.pdf", "application/pdf", b"%PDF-1.7\ngarbage", 422),
    ],
)
def test_bad_uploads_leave_no_state(
    client: TestClient, config: Settings, filename: str, mime: str, payload: bytes, code: int
) -> None:
    response = client.post("/api/papers/upload", files={"file": (filename, payload, mime)})
    assert response.status_code == code
    assert client.get("/api/papers").json()["total"] == 0
    assert not list(config.upload_dir.glob("*"))


def test_duplicate_names_are_independent(
    client: TestClient, pdf_bytes: bytes, config: Settings
) -> None:
    ids = [
        client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()["id"]
        for _ in range(2)
    ]
    assert ids[0] != ids[1]
    assert len(list(config.upload_dir.iterdir())) == 2


def test_limits_and_missing_papers(client: TestClient, config: Settings) -> None:
    config.max_file_size_mb = 1
    response = client.post(
        "/api/papers/upload", files={"file": ("large.pdf", b"%PDF-" + b"x" * 1024 * 1024)}
    )
    assert response.status_code == 413
    assert not list(config.upload_dir.glob("*"))
    assert client.get(f"/api/papers/{uuid4()}").status_code == 404
    assert client.get("/api/papers/not-a-uuid").status_code == 422
    assert client.get("/api/papers?limit=101").status_code == 422


def test_database_failure_cleans_up(
    client: TestClient,
    pdf_bytes: bytes,
    config: Settings,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit(self: Session) -> None:
        raise OperationalError("hidden query", {}, Exception("secret-password"))

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        response = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    assert response.status_code == 503
    assert "secret-password" not in response.text
    assert not list(config.upload_dir.iterdir())
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Paper)) == 0


def test_delete_is_retryable_after_storage_failure(
    client: TestClient,
    pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()[
        "id"
    ]

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("file is locked")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_unlink)
        assert client.delete(f"/api/papers/{paper_id}").status_code == 503
    assert client.get(f"/api/papers/{paper_id}").json()["processing_status"] == "deleting"
    assert client.delete(f"/api/papers/{paper_id}").status_code == 204


def test_delete_refuses_unsafe_stored_path(
    client: TestClient,
    pdf_bytes: bytes,
    session_factory: sessionmaker[Session],
) -> None:
    paper_id = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()[
        "id"
    ]
    with session_factory() as session:
        paper = session.get(Paper, UUID(paper_id))
        assert paper
        paper.file_path = "../user-file.pdf"
        session.commit()
    assert client.delete(f"/api/papers/{paper_id}").status_code == 409


def test_unconfigured_database(config: Settings) -> None:
    with TestClient(create_app(config)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/papers").status_code == 503
