# ScholarGraph

An AI research intelligence system for searching, comparing, and reasoning across scientific papers with citation-grounded retrieval.

## Development status

From the landing page, open **Library** to upload PDFs or read a paper record.
Use **Evaluation** for the historical synthetic retrieval and Q&A baselines.
The newer passage-level evaluation is recorded in [evaluation results](docs/evaluation.md).
The research workspace supports PDF upload, dense/BM25/hybrid search, grounded
Q&A, and side-by-side paper comparison. To compare, select **2–4 papers** in the
library, open **Compare papers**, and choose a topic. Run another topic to add
a row for the same papers. Select a citation to inspect its passage and PDF page.
Run the demo using [the setup and walkthrough](docs/demo.md).

![Real local search interface](docs/images/search-desktop.png)

![Answer with inspectable sources](docs/images/answer-desktop.png)

These screenshots were captured during the September local demo. The current workspace
also includes comparison, paper records and graph exploration.

**Demo GIF placeholder — recording pending.**

The full Docker Compose stack and local PostgreSQL integration passed on November 14,
including real PDF ingestion, embeddings, a cited answer and data persistence after restart.
The explicit SQLite launcher remains available for a lightweight local trial.
The November 15 GitHub Actions run passed backend, frontend and Docker checks.
[View the verified run](https://github.com/Sunilcharan711/scholargraph/actions/runs/43685954899)

Answer quality remains a development priority. A seven-question synthetic evaluation
found three false abstentions and several irrelevant citations.

See [verification and evaluation](docs/evaluation.md) for measured results and limits.

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
- BM25 keyword search and hybrid Reciprocal Rank Fusion with optional rank/score diagnostics.

- Local Ollama answers, source-ID validation, evidence excerpts and PDF page links.
- Comparison of 2–4 papers across eight dimensions with per-cell evidence.
- Semantic graph neighborhoods with similarity thresholds and keyboard navigation.
- Paper records, scoped navigation, retrieval diagnostics and historical evaluation views.
- Optional local cross-encoder reranking and reproducible evaluation scripts.

Open **Explore Scholar Graph** in the workspace to discover related papers, inspect
their similarity scores, and follow a link to another paper's neighborhood.

## Architecture

```mermaid
flowchart LR
    PDF --> Validation --> Parser[PyMuPDF parser]
    Parser --> Chunks[Page and section-aware chunker]
    Chunks --> DB[(PostgreSQL)]
    Chunks --> Embeddings --> pgvector --> Dense[Exact cosine search]
    Chunks --> BM25
    Dense --> Fusion[Hybrid retrieval / RRF]
    BM25 --> Fusion
    Fusion --> Reranker[Optional reranker] --> LLM[Provider abstraction]
    LLM --> Answer[Validate claims and map citations]
```

The [architecture guide](docs/architecture.md) explains ingestion, indexing, retrieval,
generation, comparison, graphs and deployment. A query is embedded for dense search,
tokenized for BM25, and fused by rank. An optional cross-encoder reorders candidates.
Chat loads bounded source excerpts, asks the model for structured claims and maps
validated source IDs to stored PDF pages.

Current stack: Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic,
psycopg, PostgreSQL/pgvector, PyMuPDF, sentence-transformers, PyTorch, pytest, httpx, and Ruff.
Frontend: Next.js, React, TypeScript, and responsive CSS. BM25 and RRF run locally; optional cross-encoder reranking is available via the API when configured. Docker configuration and GitHub Actions checks are included; execution status is documented below.

## Repository structure

```text
backend/
  app/
    api/          Health, papers, search, chat, comparison and graph routes
    core/         Settings, logging, upload body limit, domain errors
    db/           Declarative base and session dependencies
    models/       Papers, chunks and research graph records
    schemas/      Public response models
    ingestion/    Storage validation, parser, chunker
    retrieval/    Embeddings, pgvector search, BM25, fusion and reranking
    services/     Ingestion, indexing, and deletion workflows
    main.py       Application factory
  alembic/        PostgreSQL migration
  tests/          Unit, API, and opt-in PostgreSQL checks
  pyproject.toml  Dependencies and tool configuration
  uv.lock         Resolved development dependencies
  Dockerfile
frontend/         Next.js research workspace and browser tests
scripts/          Real-model/API smoke check and explicit paper indexing
evaluation/       Authored questions and passage relevance labels
docs/             API, architecture, and milestone verification notes
reports/          Generated local results, excluded from Git
```

## Installation and local development

Install Python 3.11+ and `uv`. From the repository root, copy the configuration
**only if you do not already have a .env**:

```powershell
Copy-Item .env.example .env
uv sync --project backend --python 3.12
```

On macOS/Linux use `cp .env.example .env`. Dependencies are resolved in `backend/uv.lock`.
Use `uv sync --project backend --python 3.12 --locked --extra cpu` for the CPU
option used by Docker and CI. Include `--extra cpu` in subsequent
`uv run --project backend` commands to retain that option.

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

In another terminal, run `npm ci --prefix frontend` and
`npm run dev --prefix frontend`, then open [ScholarGraph](http://localhost:3000).
Install Node.js 22+ and npm first. Generated answers require a running Ollama
server and the configured model, for example `ollama pull qwen2.5:1.5b`.
The [walkthrough](docs/demo.md) covers model startup and sample questions.

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

### Docker stack

With `POSTGRES_PASSWORD` set in `.env`:

```sh
docker compose up --build
```

Compose configures PostgreSQL/pgvector, waits for database health, runs migrations,
and waits for backend readiness before starting the frontend. Database, upload and
model-cache data use separate named volumes. Ports bind to localhost. The frontend
is served on localhost:3000. See [Docker setup and verification](docs/milestone-11.md)
for model configuration, health checks, persistent storage and shutdown commands.

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
  "mode": "hybrid",
  "diagnostics": true
}
```

Results contain paper/chunk IDs, title, page, section, a snippet, and a mode-specific score.
Use `dense`, `bm25`, or `hybrid`. `score_type` distinguishes cosine, BM25, and RRF scores.
The existing `similarity_score` field remains populated only for dense mode.
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
| LLM_PROVIDER / CHAT_MODEL | ollama / qwen2.5:1.5b in the template; local generation |
| OLLAMA_URL | http://127.0.0.1:11434 for the native backend |
| DOCKER_OLLAMA_URL | http://host.docker.internal:11434 for the Compose backend |
| EMBEDDING_MODEL | sentence-transformers/all-MiniLM-L6-v2; configurable Hub repository ID |
| EMBEDDING_REVISION | main; resolved commit is recorded with each vector |
| EMBEDDING_DEVICE | cpu; native runtimes may select another supported device |
| EMBEDDING_BATCH_SIZE | 32 |
| SEARCH_CANDIDATE_LIMIT | 50 candidates per method for hybrid, at least top_k; maximum 200 |
| RRF_K | 60; positive rank-fusion constant |
| EMBEDDING_CACHE_DIR | data/models, relative to repository root |
| EMBEDDING_LOCAL_FILES_ONLY | false; set true after the model cache is populated |
| RERANKER_MODEL | Optional cross-encoder model ID; disabled by default |
| RERANKER_REVISION / RERANKER_LOCAL_FILES_ONLY | main / false; model revision and offline loading |
| RERANKER_CANDIDATE_LIMIT / RERANKER_BATCH_SIZE | 20 / 8; bounded inference work |
| GRAPH_MIN_SIMILARITY / GRAPH_MAX_NEIGHBORS / GRAPH_MAX_PAPERS | 0.45 / 5 / 200 |

No real credentials, uploaded PDFs, generated data, or local databases belong in Git.

## Testing

```sh
uv run --project backend pytest -c backend/pyproject.toml
uv run --project backend ruff check backend scripts
uv run --project backend ruff format --check backend scripts
npm run lint --prefix frontend
npm run build --prefix frontend
npm run typecheck --prefix frontend
cd frontend
npx playwright install chromium
npm run test:e2e
cd ..
```

With Docker running, use `python scripts/check_docker.py` to verify its endpoints.
GitHub Actions runs backend, frontend and Docker jobs on pushes and pull requests.
Local Linux verification passed 124 backend tests, plus the separate PostgreSQL
integration check, and 22 browser tests. Browser tests use mocked API fixtures.
[CI details](docs/milestone-12.md)

The normal suite generates original tiny PDFs in temporary directories and uses
SQLite with foreign keys enabled for database-backed API tests. PostgreSQL is the
only supported production database; the SQLite vector-to-JSON variant is used by tests and the explicit local demo launcher.
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

## Evaluation and benchmark results

The November 12 retrieval run used three original synthetic PDFs and six answerable,
hand-authored questions. Scores below are macro averages for labeled passages at K=5.

| Method | Precision | Recall | MRR | nDCG |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.233 | 1.000 | 0.917 | 0.949 |
| Dense | 0.200 | 0.917 | 0.917 | 0.898 |
| Hybrid | 0.233 | 1.000 | 1.000 | 0.987 |

A separate seven-question Qwen2.5 1.5B run was reviewed by Codex against the supplied
passages. Three responses addressed the question or correctly abstained, and 3 of 11
attached citations directly supported their claim. Median total request latency was
4.01 seconds and p95 was 37.26 seconds across seven latency samples, including the
first query. These small synthetic runs provide a reproducible baseline for improving
the system. General research-paper quality and the real cross-encoder comparison
remain unmeasured. [Methods, reproduction commands and limitations](docs/evaluation.md)

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
- Hybrid retrieval combines exact terms and semantic matches using equal-weight RRF.
  It merges bounded candidate lists by chunk ID and sorts ties deterministically.
- A small transparent BM25 implementation uses positive IDF and recomputes selected-corpus
  statistics per query. No cache invalidation is required; larger corpora need a persistent index.

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

The health endpoint reports process liveness. The backend container's readiness
check also queries the database-backed paper catalog. Docker builds use the committed
application dependency lockfiles. Two upstream test-client deprecation warnings are documented.

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
| 1 | Database schema and PDF ingestion | PostgreSQL migration/ingestion integration passed in CI |
| 2 | Embeddings and dense retrieval | Real model verified locally; pgvector passed separately in CI with test embeddings |
| 3 | BM25 and hybrid retrieval | Local tests and PostgreSQL CI integration passed |
| 4 | Optional cross-encoder reranking | API implemented; real model check pending |
| 5 | Citation-grounded RAG | Local provider and citation validation implemented; answer quality needs further work |
| 6 | Multi-paper comparison | API and workspace implemented |
| 7 | Related papers and graph | Semantic graph API, saved snapshots, and neighborhood explorer implemented |
| 8 | Research interface | Landing, library, paper records, scoped chat, search diagnostics, comparison, interactive graph and recorded evaluation dashboard |
| 9 | Retrieval, generation, and latency evaluation | Labeled synthetic cases, retrieval metrics, reviewed answers and latency scripts implemented; real reranker measurement pending |
| 10 | Broader testing and quality | Backend regression tests, frontend ESLint, TypeScript, production build and desktop/mobile checks enforced in CI |
| 11 | Full Docker Compose stack | Built and verified locally with PostgreSQL, real embeddings, cited answers and restart persistence |
| 12 | GitHub Actions | Backend, frontend and full Docker startup/restart checks configured on pushes and pull requests |
| 13 | Final documentation | Architecture, retrieval, API, evaluation, setup and limitations documented |

Screenshots show the actual local demo. A demo recording and broader generation evaluation
remain pending; see [the small synthetic evaluation](docs/evaluation.md).

Remaining work includes stronger answer and citation quality, real cross-encoder
measurement, evaluation on a larger independently labeled corpus, and a demo recording.
Multi-user authentication, deployment hardening and larger-corpus indexing remain
future scope.

## Contributing and license

Copyright (c) 2026 Sunil charan. All rights reserved. See the [copyright and permissions notice](LICENSE). This project is not offered under an open-source license. Third-party dependencies retain their respective licenses. See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance.


