# ScholarGraph frontend

Next.js, React, TypeScript and responsive CSS. Provides a paper library, PDF upload,
search modes, local model questions, and a keyboard-accessible evidence dialog.

From the repository root: `npm ci --prefix frontend`, then
`npm run dev --prefix frontend`. The backend must run on localhost:8000.
See [demo setup](../docs/demo.md) for the complete walkthrough.

Production checks: `npm run build --prefix frontend` and
`npm run typecheck --prefix frontend`. Browser tests use Playwright with mocked API
responses; install Chromium and run `npm run test:e2e --prefix frontend`.
