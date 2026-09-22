"""Central settings; environment variables override the repository-root .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Validated runtime configuration, including placeholders for later milestones."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ScholarGraph"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr = SecretStr("")
    llm_provider: str = ""
    llm_api_key: SecretStr = SecretStr("")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$",
        max_length=200,
    )
    embedding_revision: str = Field(default="main", min_length=1, max_length=100)
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    embedding_cache_dir: Path = PROJECT_ROOT / "data" / "models"
    embedding_local_files_only: bool = False
    search_candidate_limit: int = Field(default=50, ge=1, le=200)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    ollama_url: str = "http://127.0.0.1:11434"
    chat_model: str = ""
    reranker_model: str = ""
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    max_file_size_mb: int = Field(default=25, ge=1, le=200)
    max_pdf_pages: int = Field(default=500, ge=1, le=2000)
    max_extracted_chars: int = Field(default=2_000_000, ge=1000, le=10_000_000)
    chunk_size_tokens: int = Field(default=400, ge=32, le=2000)
    chunk_overlap_tokens: int = Field(default=60, ge=0, le=500)

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        if not self.upload_dir.is_absolute():
            self.upload_dir = (PROJECT_ROOT / self.upload_dir).resolve()
        if not self.embedding_cache_dir.is_absolute():
            self.embedding_cache_dir = (PROJECT_ROOT / self.embedding_cache_dir).resolve()
        return self


@lru_cache
def get_settings() -> Settings:
    """Load once per process; restart after changing environment configuration."""
    return Settings()
