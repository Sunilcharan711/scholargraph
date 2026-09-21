# ScholarGraph

An AI research intelligence system for searching, comparing, and reasoning across scientific papers with citation-grounded retrieval.

## Development status

**Milestone 2: embeddings and dense retrieval implemented.** The backend supports
safe PDF upload, heuristic metadata extraction, page/section-aware chunks, paginated
paper browsing, retryable deletion, local sentence-transformer embeddings, and semantic search.
Milestones 3–13 remain planned.

Local SQLite-backed API tests exercise ingestion and cleanup. PostgreSQL/pgvector
migrations and an opt-in integration test are included, but a live PostgreSQL server
and Docker are unavailable in this environment. See [Milestone 2 verification](docs/milestone-2.md)
for exactly what was run, including real MiniLM inference. The frontend remains a placeholder.

## Features

Available:

- Validated PDF uploads with filename sanitization and generated storage names.
- Request/file size, page count, and extracted-text limits.
- PyMuPDF text extraction, probable title, metadata authors, abstract, and section headings.
- Sentence-aware chunks preserving one-based pages and section labels.
- PostgreSQL models, pgvector column, Alembic migration, cascading chunk deletion.
- Paginated list/detail APIs, structured errors, and compensating upload cleanup.
- Configurable, local sentence-transformer embeddings during ingestion.
- Exact cosine semantic search with paper filters, provenance, and timing diagnostics.
- Model/revision/dimension isolation and explicit backfill for existing paper chunks.

Planned: BM25, hybrid fusion, optional reranking, citation-grounded
answers, multi-paper comparison, related papers, an interactive graph, and evaluation.

## Architecture

```mermaid
flowchart LR
    PDF --> Validation --> Parser[PyMuPDF parser]
    Parser --> Chunks[Page and section-aware chunker]
    Chunks --> DB[(PostgreSQL)]
    Chunks --> Embeddings --> pgvector --> Dense[Exact cosine search]
    Chunks -. Milestone 3 .-> BM25
    pgvector --> Fusion[Hybrid retrieval / RRF]
    BM25 --> Fusion
    Fusion --> Reranker[Optional reranker] --> LLM[Provider abstraction]
    LLM --> Answer[Grounded answer and citations]
```

Current stack: Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic,
psycopg, PostgreSQL/pgvector, PyMuPDF, sentence-transformers, PyTorch, pytest, httpx, and Ruff.
Planned frontend: Next.js, TypeScript, Tailwind, shadcn/ui where practical, and an
interactive graph library. Planned retrieval: BM25, RRF,
and an optional cross-encoder. Docker and GitHub Actions follow the milestone roadmap.

## Repository structure

```text
backend/
  app/
    api/          Health, paper, and search routes
    core/         Settings, logging, upload body limit, domain errors
    db/           Declarative base and session dependencies
    models/       Papers and chunks
    schemas/      Public response models
    ingestion/    Storage validation, parser, chunker
    retrieval/    Embedding provider and exact pgvector search
    services/     Ingestion, indexing, and deletion workflows
    main.py       Application factory
  alembic/        PostgreSQL migration
  tests/          Unit, API, and opt-in PostgreSQL checks
  pyproject.toml  Dependencies and tool configuration
  uv.lock         Resolved development dependencies
  Dockerfile
frontend/         Explicit placeholder
scripts/          Real-model/API smoke check and explicit paper indexing
docs/             API, architecture, and milestone verification notes
```

## Installation and local development

Install Python 3.11+ and `uv`. From the repository root, copy the configuration
**only if you do not already have a .env**:

```powershell
Copy-Item .env.example .env
uv sync --project backend --python 3.12
```

On macOS/Linux use `cp .env.example .env`. Dependencies are resolved in `backend/uv.lock`.

### PostgreSQL plus native backend

Install PostgreSQL with the pgvector extension, or use Docker for the database.
Set a strong, URL-safe `POSTGRES_PASSWORD` in `.env`, then:

```sh
docker compose up -d db
```

Set `DATABASE_URL` in `.env` for the native backend:

```dotenv
DATABASE_URL=postgresql+psycopg://scholargraph:YOUR_PASSWORD@localhost:5432/scholargraph
```

Percent-encode reserved URL characters in native connection credentials. Compose's
connection string expects a URL-safe password (letters, digits, hyphens, underscores).
The migration role needs permission to install the vector extension; on managed
PostgreSQL an administrator may need to install it first.

```sh
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

Open [API docs](http://localhost:8000/docs). With an empty `DATABASE_URL`, the health
endpoint still works and paper routes return 503. The API never silently creates tables.

### Upgrading from Milestone 1

Run the migration command above to add embedding metadata. Existing chunks remain
unindexed until you explicitly run:

```sh
uv run --project backend python scripts/index_papers.py --all
```

Alternatively, use `--paper-id PAPER_UUID` (repeatable). Indexing preserves chunk IDs,
text, and provenance, committing one paper at a time. New uploads embed automatically.
The first embedding operation downloads the configured public model, then computes
vectors locally; paper text is not sent to Hugging Face. Cache files are ignored by Git.

Warm the model and verify its basic behavior without PostgreSQL:

```sh
uv run --project backend python scripts/test_dense_retrieval.py
```

After the cache is complete, set `EMBEDDING_LOCAL_FILES_ONLY=true` for offline use.
Pin `EMBEDDING_REVISION` to an immutable commit for reproducibility. If the model or
revision changes, reindex: incompatible vectors are excluded, never mixed in search.
Migration downgrade to Milestone 1 clears generated vectors and their metadata;
it preserves paper text and chunks. Back up before intentionally downgrading.

### Docker foundation

With `POSTGRES_PASSWORD` set in `.env`:

```sh
docker compose up --build
```

Compose configures PostgreSQL/pgvector, waits for database health, runs migrations,
and starts the backend. Database, upload, and model-cache data use separate named volumes. Ports
bind only to localhost. There is no frontend service yet. **This configuration has
not been executed locally because Docker is unavailable.** The single-backend migration
startup is intended for local use; coordinate migrations separately before scaling replicas.

## API usage

```sh
curl -F "file=@paper.pdf;type=application/pdf" http://localhost:8000/api/papers/upload
curl http://localhost:8000/api/papers
curl "http://localhost:8000/api/papers/PAPER_UUID?chunk_limit=20&chunk_offset=0"
curl -X DELETE http://localhost:8000/api/papers/PAPER_UUID
```

In Windows PowerShell, use `curl.exe`. Send one file per request; multiple papers
can be uploaded with separate requests. See [API contract](docs/api.md).

Search request, sent as JSON to `POST /api/search`:

```json
{
  "query": "What limitations do the authors discuss?",
  "paper_ids": [],
  "top_k": 10,
  "mode": "dense"
}
```

Results contain paper/chunk IDs, title, page, section, a snippet, and cosine similarity.
Responses also report active model identity, indexed/excluded chunk counts, and latency.
Scores are similarities, not calibrated confidence. See [retrieval design](docs/retrieval.md).

## Environment variables

Settings load the repository-root `.env`; environment variables take precedence.
Restart after changes. Relative upload paths now resolve against the repository root,
not the shell working directory. Existing Milestone 0 users should change
`UPLOAD_DIR=../data/uploads` to `UPLOAD_DIR=data/uploads`.

| Variable | Default / purpose |
| --- | --- |
| DATABASE_URL | Empty; native PostgreSQL connection; masked in settings |
| POSTGRES_PASSWORD | Required for Compose; not an application setting |
| LOG_LEVEL | INFO |
| UPLOAD_DIR | data/uploads, outside frontend assets |
| MAX_FILE_SIZE_MB | 25 (range 1–200) |
| MAX_PDF_PAGES | 500 (range 1–2000) |
| MAX_EXTRACTED_CHARS | 2000000 |
| CHUNK_SIZE_TOKENS | 400 approximate tokens |
| CHUNK_OVERLAP_TOKENS | 60; must be smaller than chunk size |
| LLM_PROVIDER / LLM_API_KEY / CHAT_MODEL | Empty; reserved for future generation |
| EMBEDDING_MODEL | sentence-transformers/all-MiniLM-L6-v2; configurable Hub repository ID |
| EMBEDDING_REVISION | main; resolved commit is recorded with each vector |
| EMBEDDING_DEVICE | cpu; native runtimes may select another supported device |
| EMBEDDING_BATCH_SIZE | 32 |
| EMBEDDING_CACHE_DIR | data/models, relative to repository root |
| EMBEDDING_LOCAL_FILES_ONLY | false; set true after the model cache is populated |
| RERANKER_MODEL | Empty; reserved for a future milestone |

No real credentials, uploaded PDFs, generated data, or local databases belong in Git.

## Testing

```sh
uv run --project backend pytest -c backend/pyproject.toml
uv run --project backend ruff check backend scripts
uv run --project backend ruff format --check backend scripts
```

The normal suite generates original tiny PDFs in temporary directories and uses
SQLite with foreign keys enabled for database-backed API tests. PostgreSQL is the
only supported production database; the SQLite vector-to-JSON variant is test-only.
Most tests inject deterministic vectors and a test-only cosine SQL function. They
exercise the production search statement's joins and filters, but not pgvector itself.

Enable actual model tests after downloading the model (PowerShell):

```powershell
$env:RUN_MODEL_TESTS = '1'
$env:EMBEDDING_LOCAL_FILES_ONLY = 'true'
uv run --project backend pytest -c backend/pyproject.toml
```

Use `RUN_MODEL_TESTS=1 EMBEDDING_LOCAL_FILES_ONLY=true uv run ...` on Unix.
The model tests cover long inputs and real PDF upload-to-search using the SQLite test adapter.

To run the PostgreSQL integration test, create a separate database whose name ends
in `_test`, with pgvector available. Set `TEST_DATABASE_URL` in the shell (not the
application's `.env`), then run:

```sh
uv run --project backend pytest -c backend/pyproject.toml -m postgres
```

The test creates and removes only its own randomly named schema, checks migrations
in both directions, compares ORM metadata, exercises the vector type, and verifies
upload/search/delete with cascading chunks. It may install the vector extension in `public`
and deliberately leaves that shared extension installed.

## Engineering Decisions

- A small synchronous ingestion service is easier to test than a queue at this stage.
  It runs in FastAPI's worker thread pool; limits bound inputs but not CPU time.
- Page boundaries are never crossed. This preserves exact page provenance for later
  citations even when it produces short chunks at page edges.
- Paragraphs and sentence boundaries guide splitting; long sentences use word windows.
  Token counts are an explicit approximation, not an embedding tokenizer guarantee.
- PDF metadata supplies authors; publication year is left null rather than treating
  a file creation date as publication evidence. Headings and titles remain heuristic.
- Uploads commit paper and chunks together; failed parsing or transactions trigger file cleanup.
  Deletion first persists `deleting`, making storage failures retryable.
- Embeddings carry an immutable resolved revision, pooling-policy version, and dimension.
  Exact cosine search is simple and deterministic for an initial small corpus; approximate
  vector indexes are deferred until corpus size and recall/latency measurements justify them.
- Long chunks are split into model-token-budgeted windows, then combined using a
  token-weighted mean and normalized. Every window contributes without changing chunk IDs.
- Hybrid retrieval is planned because exact terms and semantic similarity have different
  strengths; RRF combines ranks without assuming raw scores have comparable scales.

## Limitations and Failure Cases

No OCR, perfect multi-column/table extraction, background ingestion jobs, user accounts,
rate limiting, or public-deployment hardening exists yet. Password-protected and textless
PDFs are rejected. Mixed scanned/text PDFs include a warning for pages without text.
PDF parsing is native code; hostile inputs need process isolation/timeouts before public use.

The upload middleware spools at most the file limit plus 64 KiB of multipart overhead;
individual file limits are also checked. Parsing uses a bounded file-sized byte buffer
to avoid Windows handle leaks on malformed PDFs. Limits apply per request, not across
concurrent uploads. Reverse-proxy limits and concurrency controls remain future work.

Filesystem and database operations cannot form one atomic transaction. Process crashes,
unavailable storage during rollback, or an ambiguous database commit can require manual
reconciliation. Preserve backups; inspect `deleting` records and application logs when
recovering. Never treat an unreferenced file as safe to delete without investigation.

The health endpoint is liveness only, not database readiness. Docker dependencies use
bounded package ranges rather than a locked image build; reproducible image hardening
remains part of Milestone 11. Two upstream test-client deprecation warnings are documented.

Dense-only retrieval can miss exact identifiers or rare technical terms. Window averaging
can dilute a small relevant passage. A similarity score is not evidence that a claim is true.
Model loading and inference are synchronous and serialized per process; cold starts are
slower and multiple workers each hold a model copy. Supported models must load as text
SentenceTransformers with safetensors and no remote code; task-specific prompts are not
applied. Arbitrary model compatibility is not guaranteed. See [retrieval notes](docs/retrieval.md).

## Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| 0 | Foundation, settings, health API | Verified |
| 1 | Database schema and PDF ingestion | Implemented; live PostgreSQL verification pending |
| 2 | Embeddings and dense retrieval | Implemented; real model verified, live pgvector pending |
| 3 | BM25 and hybrid retrieval | Planned |
| 4 | Optional cross-encoder reranking | Planned |
| 5 | Citation-grounded RAG | Planned |
| 6 | Multi-paper comparison | Planned |
| 7 | Related papers and graph | Planned |
| 8 | Next.js frontend | Planned |
| 9 | Retrieval, generation, and latency evaluation | Planned |
| 10 | Broader testing and quality | Planned |
| 11 | Full Docker Compose stack | Planned |
| 12 | GitHub Actions | Planned |
| 13 | Final documentation | Planned |

Screenshots and a demo recording will be added when a working interface exists.
There are no retrieval benchmarks or generation evaluation results yet.

## Contributing and license

Copyright (c) 2026 Sunil charan. All rights reserved. See the [copyright and permissions notice](LICENSE). This project is not offered under an open-source license. Third-party dependencies retain their respective licenses. See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance.


