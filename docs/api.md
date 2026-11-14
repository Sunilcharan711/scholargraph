# API contract — Milestone 3

All endpoints are under `/api`. No authentication is implemented; run locally only.
Errors use `{"detail":"..."}`; request-schema errors use FastAPI's structured detail list.

## GET /health

Returns 200 with `{"status":"ok"}`. This is liveness, not database readiness.

## POST /papers/upload

Multipart form field `file`, one PDF per request. Success: 201 with a paper record.
Accepts application/pdf, missing MIME, or application/octet-stream, then verifies PDF
signature and parses the document. Extension must be .pdf, case-insensitive.

The response includes `id`, `title`, `authors`, `abstract`, nullable `publication_year`
and `source_url`, sanitized `filename`, `uploaded_at`, `processing_status`, and
`metadata_json` (page count, chunk count, byte count, sections, extraction warnings,
and chunk configuration). Storage paths are never exposed.

New `ready` uploads include embeddings. Legacy Milestone 1 records may still have null
vectors until explicitly indexed. Metadata includes embedding model identity, dimensions,
and embedding time after indexing. First upload/search may incur a model download and load.
Publication year and source URL remain null unless a later workflow supplies them.
One request per paper supports multi-paper upload without an ambiguous batch transaction.

Errors:

- 413: request/file bytes, page count, or extracted text exceeds configured limits.
- 415: extension, MIME type, or PDF signature is invalid.
- 422: malformed, password-protected, textless PDF, or invalid request schema.
- 503: database unconfigured/unavailable, missing migrations, storage unavailable, or model failure.

## GET /papers?limit=20&offset=0

Returns `{items: [...], total: N, limit: 20, offset: 0}`. Limit range: 1–100;
offset must be nonnegative. Sorted by uploaded_at descending, then UUID descending.
`deleting` records remain visible so failed deletions can be retried.

## GET /papers/{paper_id}?chunk_limit=20&chunk_offset=0

Returns a paper plus `chunk_count` and a paginated `chunks` array. Each chunk has
`id`, `paper_id`, one-based `page_number`, nullable `section_title`, zero-based
`chunk_index`, `text`, approximate `token_count`, and `created_at`.

Chunk limit range: 1–100; offset must be nonnegative. Chunks sort by chunk_index.
Metadata preserves section summaries without requiring every chunk in one response.
Unknown UUID returns 404; malformed UUID returns 422.

## DELETE /papers/{paper_id}

Returns 204 with no body. Removes the stored PDF and cascades deletion to chunks.
Unknown papers return 404. Invalid/unsafe stored paths return 409 without touching files.

The server commits the `deleting` status before unlinking the PDF. A filesystem failure
returns 503 and retains the record. Retrying the same DELETE completes cleanup; a missing
file is tolerated. A failed final database operation similarly leaves a retryable record.
After successful deletion, subsequent DELETE requests return 404.

## POST /search

```json
{"query":"What limitations do the authors discuss?","paper_ids":[],"top_k":10,"mode":"hybrid","diagnostics":true}
```

Query is trimmed, 1-2000 characters. top_k is 1-50. paper_ids accepts at most 100 UUIDs;
empty means all ready papers. Duplicate IDs are removed; unknown IDs match nothing.
Modes: dense (default), bm25, hybrid. Unknown modes/properties and malformed IDs return 422.

All results contain paper_id, title, chunk_id, page, section, snippet (leading 1200 characters),
score and score_type. Results sort by descending score, then chunk UUID. The dense-only
similarity_score field is retained for compatibility and is null in other modes.

| Mode | score_type | score semantics |
| --- | --- | --- |
| dense | cosine | Cosine similarity [-1,1], not confidence |
| bm25 | bm25 | Positive BM25 score; only chunks matching a query term are returned |
| hybrid | rrf | Sum of 1/(RRF_K + rank) over contributing lists |

With diagnostics=true, each result includes dense_rank, dense_score, bm25_rank,
bm25_score and fused_score. Absent signals are null, not zero. Ranks are one-based
positions in the candidate lists, before final fusion/top_k. With diagnostics=false
(default), the diagnostics field is null.

Response metadata includes query/mode, embedding_model/dimensions, indexed_chunk_count,
excluded_chunk_count, embedding_ms, dense_ms, bm25_ms, fusion_ms, retrieval_ms, latency_ms,
candidate_limit and rrf_k (null outside hybrid). BM25 has null model metadata and zero
embedding time. dense_ms excludes query embedding; retrieval_ms combines the retrieval
stages and fusion. End-to-end service time includes embedding; HTTP transfer is excluded.

For dense/hybrid, indexed/excluded counts describe dense-vector eligibility among selected
ready chunks. A chunk excluded from dense may still appear through BM25 in hybrid.
For BM25, indexed_chunk_count covers all selected ready chunks; excluded_chunk_count is zero.

Hybrid retrieves max(top_k, SEARCH_CANDIDATE_LIMIT) candidates per method (default 50),
fuses by chunk ID with RRF_K=60, then applies top_k. The lexical method can search null
or other-model vectors. Both methods enforce selected paper IDs and ready status.
BM25 computes statistics within that filtered corpus. No implicit indexing is performed.

Empty collections/unknown paper filters return 200 with no results. Dense/hybrid still
require a functioning model. Model failures return 503, with no silent lexical-only
fallback. BM25 does not load the model and can run with an empty model cache.

## Demo answers and source files

`POST /api/chat/query` accepts `question` (1–2000 characters), `paper_ids`,
`top_k` (1–12, default 6), and `mode` (default hybrid). Returns `answer`,
`citations`, `insufficient_evidence`, `latency_ms`, and `model`.
Citations include source number, paper/chunk IDs, title, page, section, excerpt,
and retrieval score. Empty evidence abstains without calling the model. Invalid
source IDs return 502; missing/unavailable model configuration returns 503.

`GET /api/papers/{paper_id}/pdf` serves the stored PDF inline with safe path checks.
`GET /api/status` reports the storage mode and configured answer provider/model;
it does not assert that the model is loaded or available.

### Q&A reliability update (October 14, 2026)

Chat responses additionally expose `retrieval_ms` (search plus evidence preparation),
`generation_ms` (provider call including any cold load), and `evidence_count`.
The service retrieves at most `min(50, 3 * top_k)` candidates and retains at most
`top_k` substantive, unique excerpts under the existing 16,000-character total and
4,000-character per-passage limits. New uploads record the origin of the title in
`metadata_json.title_source` (`metadata`, `first_page`, or `filename`). In multi-chunk
papers, excerpts matching a known PDF metadata title are omitted. Text used as an
inferred title remains eligible as evidence, including in older records of unknown origin.

Source IDs are restricted to supplied evidence in the provider's JSON schema and
validated again before response assembly. Non-integer source IDs, blank claims,
invalid JSON, truncated output and provider failures produce explicit errors.
Grouped numeric citation markers invented inside claim text are rejected as well.
No response is silently replaced with a fabricated or extractive answer.

These checks establish source identity and response shape, not semantic entailment.
Small local models can still abstain incorrectly or cite a passage that does not
support the answer. Use `scripts/evaluate_qa.py` for opt-in local-model verification;
it creates a temporary synthetic corpus and does not alter the user's library.

## POST /compare

`POST /api/compare` accepts 2–4 distinct ready paper UUIDs and a topic:

```json
{"paper_ids":["b0becd61-5769-41b9-927d-1cc55069d6b3","809c0534-039a-48d1-b553-5c154e675d5c"],"dimension":"methodology","mode":"hybrid"}
```

Replace both example IDs with IDs from the library. Topics: objective, methodology,
dataset, architecture, evaluation, findings, limitations, future_work. Each request
returns one row with cells in the supplied paper order. Each cell contains the
paper ID, title and a grounded chat response with page citations, or a provider
error. An insufficient-evidence answer means the retrieved passages did not answer
the question; it does not establish that the paper never discussed the topic.

Methodology and findings cells display sentences from retrieved passages. In the
answer text, `〔14〕` denotes numeric brackets copied from the paper; `[1]`
denotes ScholarGraph's link to an evidence passage. The snippet keeps its
original punctuation. Methods
prefer labeled methods sections. Findings use conservative English outcome cues
and can miss results, particularly in tables or with unfamiliar phrasing. They
exclude explicit plans and prior-work statements and retain qualifications
attached to measured outcomes. A paper's
explicit statement that it reports no measurements can be quoted with its citation;
silence alone produces an insufficient-evidence cell. To repeat the
local-model regression check, run `scripts/check_comparison_quality.py` in the
backend environment with Ollama configured and the embedding model cached.
## Scholar Graph

`GET /api/graph` returns ready papers and undirected semantic similarity edges.
`GET /api/graph/{paper_id}` returns the selected paper and its direct neighbors
(404 for a missing or deleting paper). Both accept `min_similarity` from 0 to 1.
Nodes include title, authors, nullable publication year, available PDF keywords,
and whether the paper has a usable pooled embedding. Missing metadata stays empty.

Chunk vectors are weighted by token count, summed and normalized. Only papers
with complete vectors in the same model revision and dimensions can link. Edges
are selected by descending cosine similarity with deterministic ID tie breaks
and a degree cap at both endpoints in the overview. The focused endpoint ranks
the selected paper's own neighbors independently and returns up to the same cap.
Scores within 1e-12 of 1 are treated as 1 before filtering. Links indicate related content, not citations.
Defaults: minimum similarity 0.45, 5 neighbors, latest 200 ready papers. Configure
`GRAPH_MIN_SIMILARITY`, `GRAPH_MAX_NEIGHBORS`, and `GRAPH_MAX_PAPERS` to change these.
If the window is truncated, the response says so; a focused request always includes
its paper. GET reads current embeddings without invoking a model or writing to storage.

`POST /api/graph/rebuild` replaces the saved semantic edges for the default window
in one transaction. GET does not depend on rebuilding a snapshot. PostgreSQL
installations must apply Alembic migration `0003_research` before saving snapshots.
