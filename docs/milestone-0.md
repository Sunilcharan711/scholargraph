# Milestone 0 verification

Verified locally on 2026-09-21 using Windows, Python 3.12.10, and the resolved
packages in backend/uv.lock.

## Implemented

- FastAPI application factory and typed GET /api/health response.
- Centralized Pydantic Settings, masked credential fields, and upload-limit validation.
- Standard-library console logging configured at application startup.
- Health endpoint and configuration tests.
- Backend packaging, development dependency lockfile, Ruff configuration.
- Initial README, contribution guide, license file, environment template, and Git ignores. The original MIT permission grant was subsequently replaced at the owner's request; see the current LICENSE file.
- Base backend Dockerfile, API-only Compose, and explicit frontend placeholders.

## Checks actually run

| Check | Result |
| --- | --- |
| uv sync --project backend --python 3.12 | Successful |
| uv run --project backend pytest | 5 passed |
| uv run --project backend ruff check backend | Passed |
| uv run --project backend ruff format --check backend | Passed; 9 files formatted |
| Uvicorn + real HTTP GET /api/health | HTTP 200 with exact JSON {"status":"ok"} |
| Real HTTP GET /openapi.json | Health endpoint present |

The smoke server used localhost port 8765 and was stopped after verification.
The environment sandbox blocked installed executables; checks succeeded with
approved execution outside that sandbox.

## Remaining limitations

Docker is unavailable on this machine; neither container build nor Compose startup
has been executed. The container files are foundation configuration, not a verified
three-service stack. No frontend runtime exists yet.

Tests emit two upstream deprecation warnings: Starlette recommends httpx2 for its
test client, and its BlockingPortal type alias is deprecated by AnyIO. The current
httpx-based tests pass. Revisit dependency compatibility before expanding integration
tests; warnings have not been suppressed.

No database, migrations, PDF ingestion, embeddings, LLM integration, or retrieval
were implemented or tested. Those belong to subsequent milestones.

## Suggested commit

`chore: initialize ScholarGraph foundation with tested FastAPI health endpoint`

No commit was created. Milestone 1 requires an explicit request to continue.

