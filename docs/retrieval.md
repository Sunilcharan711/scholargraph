# Dense retrieval — Milestone 2

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
BM25 and hybrid retrieval are reserved for Milestone 3. Multilingual, domain-specific,
and prompt-dependent models need separate compatibility and quality checks.

When excluded_chunk_count is nonzero, run indexing for the desired model/revision.
Search never reindexes or downloads papers implicitly. Model-load failures return a safe
503 error, not a fallback hash vector or fabricated search result. Complete the model cache
before enabling EMBEDDING_LOCAL_FILES_ONLY; partial caches fail explicitly.

## References

- [SentenceTransformer API](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
- [Sentence Transformers embedding and sequence-length guidance](https://www.sbert.net/examples/sentence_transformer/applications/computing-embeddings/README.html)
- [pgvector operators, exact search, and mixed dimensions](https://github.com/pgvector/pgvector)
