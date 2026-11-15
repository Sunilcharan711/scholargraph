# Milestone 12 — GitHub Actions

The Verify ScholarGraph workflow runs on pushes and pull requests with read-only
repository permissions. Three jobs run independently.

- Backend installs locked CPU dependencies, checks Python lint and formatting,
  and runs pytest with a disposable PostgreSQL/pgvector database.
- Frontend installs from the npm lockfile, checks ESLint, builds the production
  app, checks TypeScript, and runs desktop/mobile Chromium regressions.
- Docker builds both production images, starts the complete Compose stack,
  waits for healthy services, and checks the frontend, API proxy and database
  endpoints. It restarts the stack and repeats the checks.

Jobs have bounded timeouts. Failed browser tests upload traces. Failed Docker
checks upload container logs and service status. The Docker job always attempts
to remove its disposable containers and volumes.

CI uses a fixed password for its temporary database. Application secrets and local
uploaded papers are excluded from the repository. Docker smoke checks cover startup,
migrations and proxy routing. They do not require downloadable embedding weights or
a running Ollama model. Real-model upload, search, answer and persistence verification
performed locally is recorded in [Milestone 11](milestone-11.md).

View runs in the repository's Actions tab and inspect each job's failing step when
a check fails. The workflow definition is [ci.yml](../.github/workflows/ci.yml).
