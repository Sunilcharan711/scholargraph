import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "42")
    monkeypatch.setenv("LLM_API_KEY", "test-only-secret")
    settings = Settings(_env_file=None)
    assert settings.max_file_size_mb == 42
    assert "test-only-secret" not in repr(settings)


@pytest.mark.parametrize("value", [0, -1, 201])
def test_invalid_upload_limit(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_file_size_mb=value)


def test_overlap_must_be_less_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="smaller"):
        Settings(_env_file=None, chunk_size_tokens=32, chunk_overlap_tokens=32)


def test_relative_upload_path_is_anchored_to_repository() -> None:
    from app.core.config import PROJECT_ROOT

    settings = Settings(_env_file=None, upload_dir="data/uploads")
    assert settings.upload_dir == (PROJECT_ROOT / "data/uploads").resolve()
