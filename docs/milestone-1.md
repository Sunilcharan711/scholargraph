# Milestone 1 verification

Implemented on 2026-09-21. Milestone 2 has not started.

## Scope delivered

- SQLAlchemy Paper and PaperChunk models with UUIDs, JSON metadata, timestamps,
  provenance fields, nullable vectors, indexes, constraints, and cascading deletion.
- Alembic upgrade/downgrade for PostgreSQL and the pgvector extension.
- Request-body and PDF file size limits, signature/MIME/extension checks, exclusive
  generated filenames, safe storage-path validation, and rejection cleanup.
- PyMuPDF metadata/text extraction with original page numbers and heuristic sections.
- Sentence/paragraph-aware chunking, configurable approximate token budget and overlap.
- Upload, paginated list/detail, and retryable delete endpoints with safe errors.
- PostgreSQL/pgvector Compose service and persistent database/upload volumes.
- Updated README, API documentation, architecture notes, and contribution guidance.

## Executed checks

Environment: Windows, Python 3.12.10, dependencies recorded in backend/uv.lock.

| Check | Result |
| --- | --- |
| uv sync --project backend --python 3.12 | Passed |
| uv run --project backend pytest -c backend/pyproject.toml | 35 passed, 1 skipped |
| uv run --project backend ruff check backend | Passed |
| uv run --project backend ruff format --check backend | Passed |
| PostgreSQL Alembic SQL generation | Passed via subprocess test |
| Actual PyMuPDF parsing of generated two-page PDFs | Passed |
| API upload → list → detail → delete, with persisted chunks | Passed against temporary SQLite |
| Transaction failure and malformed-PDF cleanup | Passed |
| Retrying deletion after a filesystem error | Passed |
| Chunked upload request-body cap | Passed |

The local API tests use real PyMuPDF, real HTTP/ASGI request handling, real SQLAlchemy
transactions, SQLite foreign keys, and real temporary file storage. Only explicit
failure-path tests inject errors. Original fixture PDFs are generated during tests;
no copyrighted papers are committed.

## Bug found and fixed during verification

PyMuPDF's failed native file open could retain a Windows file handle for malformed
PDFs, preventing rejection cleanup. Parsing now uses a size-bounded byte buffer so
the filesystem handle is closed before native parsing. The malformed-upload test
verifies no paper row or stored PDF remains. Image payloads are excluded from text
extraction dictionaries to avoid unnecessary image-memory overhead.

Exclusive filename collisions are also tested: a failed exclusive open never deletes
the pre-existing file. A chunk-boundary test initially used a budget that fit both
sentences; its fixture budget was corrected to actually test a boundary.

## Not verified here

Docker and PostgreSQL executables/server are unavailable. The real PostgreSQL test
is explicitly skipped without TEST_DATABASE_URL. Offline SQL generation and SQLite
API tests do not establish that PostgreSQL migration execution, vector operations,
Docker image construction, or Compose startup work on this host.

The opt-in PostgreSQL test is included in backend/tests/test_postgres.py. It requires
a disposable database name ending in `_test`, uses a unique schema, runs migration
upgrade/downgrade/upgrade, checks model/schema consistency and a vector operation,
and exercises upload/delete with cascading chunks. It only drops its own schema;
the shared public.vector extension is deliberately preserved.

Two existing upstream deprecation warnings remain: Starlette's recommendation to
use httpx2 for its test client, and its use of AnyIO's deprecated BlockingPortal alias.
Neither warning is suppressed. There is no frontend runtime to test yet.

## Next verification on a Docker-capable host

1. Copy .env.example only if no .env exists; set a URL-safe POSTGRES_PASSWORD.
2. Run `docker compose up --build` and inspect database/backend health.
3. Upload an original text PDF using /docs, inspect page/section chunks, and delete it.
4. Create a separate PostgreSQL database ending in `_test`, set TEST_DATABASE_URL in
   the shell, and run `uv run --project backend pytest -c backend/pyproject.toml -m postgres`.

## Suggested commit

`feat: add PostgreSQL schema and validated PDF ingestion`

No Git commit was made. Live PostgreSQL/container verification remains pending;
no embeddings, search, or other Milestone 2 features were added.
