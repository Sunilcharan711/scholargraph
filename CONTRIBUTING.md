# Contributing

Work in small, verified milestones. Read README.md for setup and current scope.
Use Python type annotations, small modules, and tests for observable behavior.
Run `uv run --project backend pytest -c backend/pyproject.toml`,
`uv run --project backend ruff check backend scripts`,
and `uv run --project backend ruff format --check backend scripts` before proposing changes.
Keep credentials, uploaded papers, model artifacts, and generated data out of Git.
Use conventional commit messages, but review changes before committing.

The normal suite uses generated PDF fixtures and a temporary SQLite database with
foreign keys enabled. Never substitute a production database for test infrastructure.
Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in `_test` to run
the opt-in PostgreSQL migration/vector/API test. See README.md for setup and scope.

Use Alembic migrations for schema changes; do not call create_all during app startup.
Keep storage paths internal, preserve page provenance, and test rejection cleanup when
changing ingestion. Frontend checks will be added when the frontend is implemented.

Embedding unit tests use clearly labeled deterministic vectors. Run the real-model
smoke script and opt-in `RUN_MODEL_TESTS=1` checks when changing the embedding adapter.
Do not substitute test vectors for production inference. Model revisions, dimensions,
and pooling policy are part of the stored embedding identity; changes require reindexing.
Model-cache and smoke-report artifacts stay ignored by Git.
