# Running the local demo

This demo covers upload, a persistent paper library, three search methods, and local
question answering with clickable page citations. Comparison, graphs, reranking,
and public multi-user hosting are outside this demo scope.

## On this Windows machine

From the repository root:

```powershell
.\scripts\start_demo.ps1
```

Open http://127.0.0.1:3000. The launcher uses installed tools, with fallbacks to the
local runtimes prepared during development. It starts hidden processes and prints
new process IDs; stop those using `Stop-Process -Id <ID>` when finished. Logs are in
`data/demo-*.log`. Already running services are reused. The launcher does not download
an answer model; this machine already has `qwen2.5:1.5b` in `data/ollama-models`.

## Fresh checkout (Windows, macOS or Linux)

Install Python 3.12, uv, Node.js 22+ with npm, and [Ollama](https://ollama.com/download).
Copy `.env.example` to `.env` only if `.env` does not exist. Never commit credentials.

```sh
uv sync --project backend --python 3.12 --locked
npm ci --prefix frontend
ollama pull qwen2.5:1.5b
```

Start Ollama if its service is not already running (`ollama serve`). Leave these two
commands running in separate terminals at the repository root:

```sh
uv run --project backend python scripts/run_demo.py
npm run dev --prefix frontend
```

For a production frontend build use `npm run build --prefix frontend` followed by
`npm start --prefix frontend`. Native frontend traffic proxies through Next.js to
`http://127.0.0.1:8000`; set `BACKEND_URL` before building to change that destination.
The browser never receives a provider API key. A first PDF upload downloads the
MiniLM model; subsequent uploads reuse its cache. Do not enable
`EMBEDDING_LOCAL_FILES_ONLY` on a fresh checkout before that download completes.

## A two-minute walkthrough

1. Generate original samples: `uv run --project backend python scripts/make_demo_papers.py`.
2. Add the three PDFs in `data/sample-papers` using **Add research papers**.
3. Search: **How does the prototype combine keyword and semantic retrieval?**
4. Compare Hybrid, Semantic, and Keyword search. Scores use different scales.
5. Switch to **Ask your library**, submit the same question, and click a citation.
6. Click **Open original PDF** to inspect the cited page.
7. Select only the greenhouse paper and ask about a subject absent from it; verify
   whether the model abstains. Inspect evidence rather than assuming the answer is correct.
8. Delete a sample using its × control and confirm that it disappears from the library.

All sample text is original and explicitly synthetic. It is not published research.
Do not upload the same samples repeatedly unless duplicate papers are intentional.

## Storage and model limits

The explicit demo launcher stores PDFs and SQLite data under `data/demo` and uses
real local sentence embeddings with exact cosine similarity in Python. It does not
run Alembic or pgvector. Do not use this launcher for a public deployment or as proof
that PostgreSQL integration passed. Existing PostgreSQL data is separate and untouched.
Demo schemas have no migration guarantee; preserve data before changing schema versions.

`LLM_PROVIDER=ollama`, `CHAT_MODEL=qwen2.5:1.5b`, and
`OLLAMA_URL=http://127.0.0.1:11434` configure answers. Larger compatible instruction
models can improve quality, at a memory/latency cost. A small model can misunderstand
a question, cite weak evidence, or fail to abstain. Source IDs are checked, but semantic
entailment is not automatically established. Model errors are explicit; no fake answer
or silent extractive fallback is substituted. Requests have a 120-second model timeout.

## PostgreSQL / Docker path

Set a strong URL-safe `POSTGRES_PASSWORD` in `.env`, then run:

```sh
docker compose up --build
```

The stack starts pgvector PostgreSQL, migrates the backend, and serves Next.js on
localhost:3000. Ollama remains on the host; backend containers use
`host.docker.internal:11434`. A host Ollama bound only to 127.0.0.1 may not accept
container connections. Configure its binding/firewall appropriately or run the native
backend for local-only Ollama. Docker and live PostgreSQL were unavailable on the
Windows development host; this path remains unverified locally. The added CI workflow
runs the disposable PostgreSQL integration test when pushed; no CI success is claimed yet.

## Verification commands

```sh
uv run --project backend pytest -c backend/pyproject.toml
uv run --project backend ruff check backend scripts
uv run --project backend ruff format --check backend scripts
npm run build --prefix frontend
npm run typecheck --prefix frontend
cd frontend
npx playwright install chromium
npm run test:e2e
```

Browser regression tests use mocked API responses to isolate interface behavior.
The screenshots in `docs/images` come from the real local API, real MiniLM embeddings,
and real Ollama generation. The retrieval check is reproducible with
`uv run --project backend python scripts/evaluate_demo.py` (see `evaluation.md`).
