# Milestone 2 verification

Implemented and checked locally on 2026-09-21. Milestone 3 has not started.

## Delivered

- Configurable sentence-transformer provider, lazy initialization, local CPU inference,
  persistent model cache, batch encoding, and typed provider injection.
- Resolved model commit plus pooling policy and dimensions stored with every vector.
- Token-budgeted windows with weighted pooling, preserving late text without changing chunks.
- Embedding generation before upload commit, with rollback/file cleanup on failure.
- Migration 0002 for embedding metadata, constraints, and model-space lookup index.
- Exact pgvector cosine search with paper/model/dimension/status filters and stable ordering.
- POST /api/search with provenance, snippets, scores, counts, and latency diagnostics.
- Explicit existing-paper backfill/reindex command preserving chunk IDs and source text.
- Real-model/API smoke script, model tests, retrieval/API tests, and PostgreSQL test expansion.
- Updated environment template, model-cache Compose volume, README, API and retrieval docs.

## Actual checks

Environment: Windows, Python 3.12.10. Resolved dependencies are in backend/uv.lock,
including sentence-transformers 5.7.0 and PyTorch 2.14.0.

| Check | Observed result |
| --- | --- |
| uv sync --project backend --python 3.12 | Passed |
| Full suite with RUN_MODEL_TESTS=1 and EMBEDDING_LOCAL_FILES_ONLY=true | 58 passed, 1 skipped |
| Additional strengthened long-input and real upload/search model checks | 2 passed |
| Ruff lint for backend and scripts | Passed |
| Ruff formatting for backend and scripts | Passed; 47 Python files |
| scripts/index_papers.py --help | Passed |
| Alembic PostgreSQL SQL generation | Passed in the test suite |
| Real model smoke script | 3 of 3 original passage/query matches ranked first |
| Real PyMuPDF upload → MiniLM embeddings → stored chunks → semantic API search | Passed with SQLite test distance adapter |

Two pre-existing upstream test-client deprecation warnings remain; neither is suppressed.
The normal offline unit suite uses deterministic test vectors. Real model tests are
explicitly enabled by RUN_MODEL_TESTS=1, rather than silently downloading models in CI.

## Real model evidence

Model identity:

```text
sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41:window-mean-v1
```

Output dimension: 384. Three deliberately small original topic pairs (solar electricity,
vaccination, database indexing) each ranked their intended passage first. This is a smoke
check, not a retrieval evaluation benchmark. The actual local report is in the ignored
reports/dense_smoke.json file. No Milestone 9 quality claim is inferred from this result.

The first smoke run measured 7015.595 ms for embedding three documents including process
model import/load and 16.222 ms for three subsequent query embeddings. These are one-run,
in-memory measurements on this host, not PostgreSQL latency, per-request throughput,
or statistically meaningful performance results.

The long-input test verifies normalized vectors, semantic similarity, and that a different
topic beyond the first model window changes the output. The API model test uploads two
original PDFs and checks that the battery-related question retrieves the battery paper.
Its database is SQLite with a test-only cosine function, not PostgreSQL.

## Download issue and recovery

Hugging Face connections were intermittently reset during the initial download.
The weight file and part of the configuration were cached, but the snapshot was incomplete.
Missing files were downloaded from the same immutable official Hub revision with Windows'
HTTP client. All 11 selected artifacts were checked against the cached Hub manifest:
SHA-256 for the safetensors weights and Git blob hashes for the other files.

The completed model was then loaded and tested entirely offline. No TLS verification was
disabled, no paper content was transmitted, and no alternate/fake model replaced MiniLM.
Model artifacts remain under ignored data/models. The production loader reports incomplete
cache/download failures as 503; users should complete the cache before enabling offline mode.

## Review fixes

- Migration downgrade now clears vectors and both metadata fields together, avoiding
  an intermediate violation of the embedding metadata consistency constraint.
- PostgreSQL tests now cover downgrade with populated vectors and subsequent reindexing.
- The newer embedding-dimension API is used when available, with compatibility fallback.
- Retrieval counts use one aggregate query; incompatible dimensions are guarded before
  cosine evaluation as well as filtered from the result set.

## Still unverified

No PostgreSQL/pgvector server or Docker runtime is available here. The PostgreSQL test was
explicitly skipped. It covers migrations, native vector cosine, model/schema consistency,
vector backfill, and upload/search/delete when TEST_DATABASE_URL points to a disposable
database ending in _test. SQLite tests and PostgreSQL SQL compilation do not prove native
pgvector execution or container startup. Neither full Docker build nor Compose was run.

## Running the new functionality

```sh
uv sync --project backend
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend python scripts/index_papers.py --all
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

Set DATABASE_URL first. Indexing is only needed for existing papers or an intentional model
change; new uploads embed automatically. The read-only server smoke mode is:

```sh
uv run --project backend python scripts/test_dense_retrieval.py --api-url http://localhost:8000
```

It requires at least one indexed paper. See README.md and docs/retrieval.md for offline
configuration, exact request/response details, and model-change limitations.

Suggested commit: `feat: add versioned embeddings and dense semantic search`

No Git commit was made. BM25, hybrid retrieval, reranking, and generation remain unimplemented.
