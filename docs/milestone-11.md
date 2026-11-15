# Docker setup

On November 14, Docker Desktop 4.99.0 and WSL were installed. After restarting
Windows, both application images built and all three Compose services became healthy.
The frontend proxy passed the stack smoke check. Three original synthetic PDFs were
uploaded through it, and dense, BM25 and hybrid searches returned the expected evidence.
The host's local Qwen2.5 1.5B model generated a cited answer whose PDF was accessible.
Paper records, chunks, PDF files and model-backed search survived a stack restart.

The Linux backend suite passed 124 tests, including cached real embeddings.
PostgreSQL migration and vector integration passed separately against a disposable
database in the Compose PostgreSQL service. All 22 desktop/mobile UI regressions
passed against the containerized frontend with their mocked API fixtures.
The real cross-encoder test remains pending model availability.

Install Docker Desktop with the WSL 2 backend on Windows, or Docker Engine and
the Compose plugin on Linux. Start Docker and confirm that `docker info` succeeds.
Windows may require a restart after enabling WSL or virtualization.

From the repository root, copy `.env.example` to `.env` if it does not already
exist. Set `POSTGRES_PASSWORD` to a long random value containing letters, digits,
hyphens and underscores. Compose inserts this value into its database URL.
Keep the populated file private.

```sh
docker compose up --build
```

Open [ScholarGraph](http://localhost:3000) and [API docs](http://localhost:8000/docs).
Ports 3000, 8000 and 5432 must be available. The initial build downloads dependencies.
The first PDF upload also downloads the embedding model unless its named cache
volume is already populated.

PostgreSQL includes pgvector. The backend applies Alembic migrations before starting
and uses the committed Python dependency lockfile with the `cpu` extra for PyTorch.
Its container health check queries
the paper catalog to verify database and schema access. The frontend starts after
backend health succeeds, uses a standalone Next.js build, and checks its API proxy.
Both application containers run as unprivileged users.

For detached startup and verification, run the following.

```sh
docker compose up --build -d --wait --wait-timeout 900
docker compose ps
python scripts/check_docker.py
```

The smoke script checks the frontend, proxied API, PostgreSQL storage and graph schema.
Upload a PDF, run a search and inspect the source evidence to check model inference.
Then restart the stack and verify that the paper and its PDF remain available.
Named volumes retain database rows, uploaded PDFs and cached models across normal
container restarts.

## Generated answers

Install Ollama on the host, pull the model named by `CHAT_MODEL`, and make its
HTTP endpoint reachable from Docker. The default container address is
`http://host.docker.internal:11434`. Set `DOCKER_OLLAMA_URL` in `.env` to use
another reachable endpoint. Native backend runs use `OLLAMA_URL`.

On this Windows installation, the container reached the host's loopback Ollama
server through `host.docker.internal` successfully.

Ollama may need to listen on a host interface reachable from the container.
Keep host firewall access limited to the local machine and Docker network.
Restart Ollama after changing its listen address. Test from the backend container.

```sh
docker compose exec backend python -c "import os,urllib.request; print(urllib.request.urlopen(os.environ['OLLAMA_URL']+'/api/tags',timeout=5).status)"
```

Search and graph exploration work independently of answer generation. Optional
reranking requires `RERANKER_MODEL` and downloaded cross-encoder weights.

## Logs and shutdown

```sh
docker compose logs --tail 100 backend frontend db
docker compose down
```

Normal shutdown retains named volumes. Adding `--volumes` removes stored database
and upload data. Back up the database and uploaded PDFs together before removing
volumes. A single backend applies migrations at startup, so coordinate migration
execution separately before running multiple backend replicas.

Base image tags can receive upstream updates. Application dependency installation
uses `uv.lock` and `package-lock.json`.

## Existing embedding cache

The model registry was unreachable during this verification, so the previously
verified MiniLM cache was copied into the named model volume. If you have the same
complete local cache, the following commands can seed it after the backend starts.

```sh
docker compose cp data/models/models--sentence-transformers--all-MiniLM-L6-v2 backend:/data/models/
docker compose exec --user root backend chown -R appuser:appuser /data/models/models--sentence-transformers--all-MiniLM-L6-v2
```

Set `EMBEDDING_LOCAL_FILES_ONLY=true` after the required model revision is cached
to run without contacting the model registry. Recreate the backend with
`docker compose up -d` after changing configuration.
