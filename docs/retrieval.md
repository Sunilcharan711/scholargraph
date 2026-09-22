# Retrieval — Milestones 2 and 3

## Embedding contract

`EmbeddingProvider` exposes a model-space identity and batch encoding method.
`SentenceTransformerEmbedder` is the production implementation; deterministic test
providers exist only under tests. The default is all-MiniLM-L6-v2, with CPU inference.
Model loading is lazy, so health and paper browsing do not download weights.

The adapter resolves a Hugging Face snapshot and records its exact commit, even when
EMBEDDING_REVISION is a moving branch such as main. The identity also includes the
window-mean-v1 pooling policy. Model dimensions are read from the loaded model.
Pin an immutable revision for repeatable indexing. Safetensors are required, and
remote model code is disabled. Symmetric text encoding is used for both documents
and queries; task-specific query/document prompts are intentionally not applied.

The first embedding operation may download weights and tokenizer/configuration files.
Paper content is encoded locally and is not uploaded to Hugging Face. A reentrant lock
serializes model initialization/inference per process. Separate server workers hold
separate model copies. Caching uses data/models by default and a named volume in Compose.

## Avoiding silent truncation

The PDF chunker preserves page and section boundaries using a word-based token estimate.
The embedding adapter separately counts actual tokenizer tokens, including special tokens.
If a chunk exceeds the model input budget, it recursively splits into whitespace-aligned
windows; unbroken text can be divided as a final fallback. A 128-window bound prevents
pathological splitting. Each window is encoded in batches, then its normalized vector is
weighted by content-token count. Their weighted mean is normalized again to create the
stored chunk vector. All text windows contribute; chunk IDs and source text remain unchanged.

This is a simple approximation: averaging can dilute a small relevant part of a long
chunk. It does not replace model-aware retrieval evaluation. Empty, non-finite, zero,
wrong-dimensional, or wrong-count embedding outputs are rejected before persistence.

## Persistence and upgrades

Each chunk stores its vector, model identity, and dimensions. The PostgreSQL vector
column remains dimensionless so deliberate model changes do not require dropping old
data. Constraints require vectors and their metadata together and verify vector dimensions.
A B-tree index on model identity/dimensions narrows the active embedding space.

New uploads embed before committing their paper and chunks. Model failures roll back
and clean up the new PDF. Existing Milestone 1 chunks remain unindexed after migration:

```sh
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend python scripts/index_papers.py --all
```

Use `--paper-id UUID` for selected papers. Reindexing replaces embeddings in one
transaction per paper while preserving chunk IDs/text. Prior successful papers remain
committed if a later paper fails. The active paper is rolled back. Indexing locks the
paper/chunk rows until completion, so plan larger backfills outside interactive use.

The migration refuses unexpected populated, unversioned vectors rather than guessing
their provenance. Intentionally downgrading to 0001 clears generated vectors and their
model metadata while preserving source records; back up before downgrading.

## Exact cosine search

POST /api/search encodes the query with the same adapter, then ranks ready paper chunks
using pgvector's cosine-distance operator. Similarity is 1 minus distance; it ranges
from -1 to 1 and is not a calibrated confidence or claim-correctness score.

Filtering occurs before top_k: selected paper IDs, ready status, non-null vector,
matching model identity, and matching dimensions. A guarded CASE expression also
prevents evaluating cosine distance on an incompatible-dimensional row if PostgreSQL
reorders execution. Ties sort by chunk UUID. Unknown but valid paper IDs match nothing.

Results include source paper/chunk IDs, title, page, section, and a leading 1200-character
snippet. Full chunk text remains available through paginated paper detail. Responses
report the active model, dimensions, indexed/excluded chunk counts for the selected ready
papers, query embedding time, database retrieval time, and total service time. Those timings
exclude HTTP body parsing/response transfer and are diagnostics, not a benchmark.

This milestone uses exact nearest-neighbor search, with no HNSW/IVFFlat approximation.
It is a correctness-oriented baseline for small collections. Corpus size, filtering,
recall, and latency measurements should drive a later approximate-index decision.

## Verification layers

- Unit tests validate vectors, full-text window coverage, failures, and configuration.
- SQLite API tests use the production query structure with a test-only cosine SQL
  function. They verify ordering, filters, model isolation, provenance, and cleanup.
- `RUN_MODEL_TESTS=1` enables actual MiniLM inference, long-input checks, and generated
  PDF upload-to-search through the SQLite test adapter.
- The opt-in PostgreSQL test runs the native vector operator, schema consistency,
  populated-vector migration downgrade/upgrade, reindexing, and upload/search/delete.
- `scripts/test_dense_retrieval.py` runs three original passage/query smoke checks with
  actual model weights; `--api-url http://localhost:8000` instead checks existing server
  data without uploading or deleting papers. Reports are saved under ignored reports/.

The smoke corpus is intentionally tiny and is not the evaluation dataset planned for
Milestone 9. It establishes basic behavior, not general research retrieval quality.

## Failure cases and model changes

Dense-only search can miss exact acronyms, names, and uncommon technical terms. Queries
without relevant material still return nearest neighbors; there is no relevance cutoff.
BM25 and hybrid retrieval are now available as complementary methods. Multilingual, domain-specific,
and prompt-dependent models need separate compatibility and quality checks.

When excluded_chunk_count is nonzero, run indexing for the desired model/revision.
Search never reindexes or downloads papers implicitly. Model-load failures return a safe
503 error, not a fallback hash vector or fabricated search result. Complete the model cache
before enabling EMBEDDING_LOCAL_FILES_ONLY; partial caches fail explicitly.

## References

- [SentenceTransformer API](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
- [Sentence Transformers embedding and sequence-length guidance](https://www.sbert.net/examples/sentence_transformer/applications/computing-embeddings/README.html)
- [pgvector operators, exact search, and mixed dimensions](https://github.com/pgvector/pgvector)

## BM25 implementation

A small typed implementation avoids an additional runtime dependency. Tokenization uses
Unicode NFKC normalization, case folding, and word tokens. Punctuation separates terms
(e.g. BERT-base becomes bert and base). No stemming, stop-word removal, phrase operator,
or query-language parsing is applied. Repeated query terms contribute only once.

For term t: IDF = ln(1 + (N - df(t) + 0.5)/(df(t) + 0.5)).
Term score = IDF * tf * (k1+1) / (tf + k1*(1-b+b*length/avg_length)).
Defaults: k1=1.5, b=0.75. Scores sum over matching terms. Positive IDF avoids negative
scores in tiny collections. Empty/tokenless/nonmatching queries produce no lexical hits.
Tests check a hand-calculated score, length normalization, and term-frequency saturation.

Each request reads selected ready chunk text and recomputes statistics; it neither loads
vectors nor keeps a cache. Committed uploads/deletions are visible on the next request.
This is deliberately a small-corpus baseline: CPU/memory cost grows with selected text
volume. Candidate limits bound fusion work, not the cost of scanning/tokenizing the corpus.
Scores change when the selected corpus changes. They are not comparable across queries.

## Shared retrieval and RRF

Retriever.retrieve(session, request, limit) returns typed RetrievalBatch/ RetrievalHit data.
DenseRetriever and BM25Retriever implement the same contract. The search service owns
mode dispatch, diagnostics, timing and response assembly, ready for reuse in later RAG.

Hybrid runs both retrievers with a candidate budget of max(top_k, SEARCH_CANDIDATE_LIMIT).
It does not truncate each list to the final top_k before fusion. Each chunk contributes
at most once per method, with one-based ranks: RRF(chunk) = sum(1/(RRF_K + rank)).
Default RRF_K=60 limits domination by a single top-ranked result; it is configurable,
not claimed as optimal for this dataset. Methods have equal weight. Final ties sort by
chunk UUID. Raw BM25/cosine scores never get added to each other.

Both methods filter papers/status consistently. Dense additionally requires a compatible
embedding space; BM25 can contribute legacy or other-model chunks. A missing rank means
not present in that candidate list, not proof of zero relevance. Hybrid model failures
return errors rather than presenting a silent single-method fallback as hybrid success.
The two legs use sequential database reads; concurrent changes can be observed between
legs under default PostgreSQL isolation. Strict snapshot consistency is not promised.

The API exposes separate raw-score/rank diagnostics and stage timings. This milestone
has correctness tests and small real-model smoke checks, not a retrieval benchmark or
proof that hybrid universally outperforms either method. Milestone 9 will measure that.
