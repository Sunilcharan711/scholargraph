# ScholarGraph frontend

Next.js, React, TypeScript and responsive CSS. Provides a paper library, PDF upload,
search modes, local model questions, and a keyboard-accessible evidence dialog.

From the repository root: `npm ci --prefix frontend`, then
`npm run dev --prefix frontend`. The backend must run on localhost:8000.
See [demo setup](../docs/demo.md) for the complete walkthrough.

Production checks: `npm run build --prefix frontend` and
`npm run typecheck --prefix frontend`, plus `npm run lint --prefix frontend`.
Browser tests use Playwright with mocked API
responses; install Chromium and run `npm run test:e2e --prefix frontend`.
## Research workspace

The landing page links to the PDF library. Open a record for its abstract,
sections, metadata, related research and paper-scoped actions. Search supports
optional rank diagnostics. The graph uses Cytoscape.js and also provides a
keyboard-accessible list of neighbors. The evaluation page shows the recorded
synthetic retrieval and Q&A baselines; it does not evaluate a user's library.
The bundled summary contains aggregate metrics, not private paper contents.

Routes: `/`, `/library`, `/papers/[id]`, `/chat`, `/search`, `/compare`,
`/graph`, and `/evaluation`. Paper-scoped chat and comparison use `?paper=<id>`.
