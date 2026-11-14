# Milestone 3 re-verification — October 13, 2026

## Repository and scope

Original local workspace: `C:\MY projects\scholargraph`, branch `main`,
HEAD `c195577be3b0918c732cef81808f9588a98caf5c`. The handoff's commit `8d2e641`
is older. Milestone 3 plus the focused Q&A/frontend demo already exist in HEAD.
They were preserved rather than rebuilt. Optional reranking remains deferred.
Session-only reranking edits were saved under ignored
`data/deferred-reranking-2026-10-13`, then removed from active application code.
Saved Python files use `.py.saved` to prevent accidental pytest collection.
No existing `.env`, application data, copyright notice, commit, or remote was changed.

## Current environment

- Python 3.12.10 in `backend/.venv`.
- uv 0.12.3.
- Node.js 24.19.0 from the local bundled runtime.
- Existing `.env` and verified MiniLM cache are present; contents of secrets were not printed.
- Docker and psql are not on PATH; the standard Docker Desktop executable is absent.
- No Docker/PostgreSQL Windows service was found with service-manager access.
- `wsl --status` reports that WSL is not installed.
- No applicable AGENTS.md was found in the project.

## Checks run locally

Real-model tests enabled with `RUN_MODEL_TESTS=1` and
`EMBEDDING_LOCAL_FILES_ONLY=true`:

| Check | Result |
| --- | --- |
| `pytest -c backend/pyproject.toml backend/tests` | 86 passed, 1 skipped |
| Real MiniLM upload/search, including dense/BM25/hybrid | Passed with SQLite adapter |
| BM25/RRF regressions | 14 passed within the full suite |
| Ruff lint | Passed |
| Ruff formatting | Passed, 60 files |
| Live PostgreSQL integration | Skipped locally: no TEST_DATABASE_URL/server |
| Local Docker build / Compose startup | Blocked: Docker/WSL absent |

Two upstream Starlette/AnyIO deprecation warnings remain. The initial recheck also
collected the saved reranking tests from ignored data; renaming the backup files and
running the explicit backend test directory fixed that test-discovery issue.
Sandbox cache/temp-directory permissions required rerunning verification outside the
sandbox; those environment errors were not treated as application test failures.

## Actual PostgreSQL evidence from existing CI

Inspected the complete job log for
[GitHub Actions run 35756595006](https://github.com/Sunilcharan711/scholargraph/actions/runs/35756595006),
which ran on September 22, 2026 against the exact current HEAD.

- Backend: **85 passed, 2 skipped**. The skipped cases were real-model tests.
- `backend/tests/test_postgres.py` passed, not skipped.
- CI started a real `pgvector/pgvector:pg17` Docker service with a disposable
  `scholargraph_test` database.
- The integration test checks live migrations, native vector cosine distance,
  ORM/schema consistency, PDF ingestion, dense/BM25/hybrid search with paper filters,
  populated-vector downgrade/upgrade, reindexing, deletion/cascade, and fresh upgrade.
- This test injects deterministic embeddings. It verifies PostgreSQL mechanics,
  not MiniLM quality or a combined real-model/native-pgvector end-to-end flow.
- Frontend build/typecheck and both browser tests also passed in that run.

This closes the previous *entirely unverified PostgreSQL mechanics* claim. It does
not establish that this Windows host can run Docker, or that the repository's
backend/frontend Dockerfiles and full Compose startup work. CI uses a database
service container, not the complete application Compose stack.

## Local setup blocker and next verification

Install WSL 2 and Docker Desktop using the official
[Docker Windows setup instructions](https://docs.docker.com/desktop/setup/install/windows-install/)
and [Microsoft WSL instructions](https://learn.microsoft.com/en-us/windows/wsl/install).
Finish any required administrator prompts or reboot, launch Docker Desktop, and
confirm `docker info` succeeds. No OS installation or restart was attempted in this pass.

Preserve the existing `.env`. Set a strong URL-safe `POSTGRES_PASSWORD` there, then:

```powershell
docker compose up -d db
docker compose exec db createdb -U scholargraph scholargraph_test
```

Create the disposable test database only once; do not drop an existing database.
Set `TEST_DATABASE_URL` privately in the terminal to the connection for
`scholargraph_test`, then:

```powershell
uv run --project backend pytest -c backend/pyproject.toml backend/tests/test_postgres.py
```

For full-stack verification, run `docker compose up --build`, check migrations and
service logs, then upload an original sample PDF and verify dense/BM25/hybrid search
and deletion. A fresh model-cache volume requires network access; if the native `.env`
has `EMBEDDING_LOCAL_FILES_ONLY=true`, override it to false for that initial download.
Never run the populated-vector downgrade checks against the application database.

Stop at Milestone 3 as requested. No new Q&A, reranking, graph, or comparison work
was added, and no commit or push was made during this pass.
