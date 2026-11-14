# Milestone 10 verification

November 14, 2026.

The backend suite covers settings, PDF validation, parsing and chunk boundaries,
dense and BM25 retrieval, hybrid fusion, reranker behavior, citation mapping,
uploads, search, health, comparison, graph behavior and evaluation metrics.
Tests exercise temporary databases and generated PDFs. The local run with
`RUN_MODEL_TESTS=1` passed 124 tests, including real cached MiniLM retrieval.
Two checks were skipped because a disposable PostgreSQL database and downloaded
cross-encoder weights were unavailable. CI supplies PostgreSQL with pgvector.

Ruff lint and formatting checks pass across backend and scripts. Frontend ESLint
uses the Next.js and TypeScript recommended rules and rejects warnings in CI.
The workspace fetch effect has one documented exception for its loading-state
update before requesting a new page. TypeScript and the production build pass.
All 22 desktop and mobile browser tests passed. Regressions include graph error recovery, scoped navigation, deletion,
comparison, search and citation inspection on desktop and mobile.

Compatible dependency updates moved the installed Next.js version to 16.4.6 and
resolved the reported high and critical npm advisories. Seven moderate findings
remain in the development lint dependency chain after compatible updates.

Run commands are in [CONTRIBUTING](../CONTRIBUTING.md). Milestone 9's real
cross-encoder measurement and the answer-quality limitations described in
[evaluation](evaluation.md) remain open.
