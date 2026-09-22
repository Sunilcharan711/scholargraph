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
