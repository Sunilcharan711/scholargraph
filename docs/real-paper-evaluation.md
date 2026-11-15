# Real-paper development evaluation

On 2026-11-15, ten version-pinned arXiv PDFs were indexed with the real
MiniLM embedding model and queried with local `qwen3:4b` (thinking disabled).
The [manifest](../evaluation/real-papers.json) records original paper links,
PDF SHA256 checksums, 14 questions, expected points and evidence anchors.
PDFs and generated reports remain local and are not redistributed in Git.

This is a small, authored development set, not an independent benchmark.
Search runs against all ten papers. Q&A is scoped to the relevant paper IDs;
its results therefore do not measure unrestricted end-to-end discovery.

## Recorded results

| Check | Baseline | After parser/duplicate fixes |
| --- | --- | --- |
| PDFs successfully ingested | 10/10 | 10/10 |
| Mean dense paper recall@5, 12 answerable cases | 1.000 | 0.917 |
| Mean BM25 paper recall@5 | 1.000 | 1.000 |
| Mean hybrid paper recall@5 | 1.000 | 1.000 |
| Missing-evidence abstention | 2/2 | Not rerun |

Paper recall measures whether relevant **papers** occur among five chunk hits.
It does not measure passage relevance, citation entailment or answer accuracy.
Evidence anchors are review aids, not an automated passage-relevance score.
After corrected font-span spacing changed chunks, dense search missed the DPR
paper for `real-04`; BM25 and hybrid still found it. This is a recorded regression,
not evidence of uniformly improved retrieval.

Baseline title extraction often selected the vertical arXiv watermark. The
parser now excludes rotated title candidates, joins wrapped title lines and
preserves contiguous words split across font spans. All ten titles were visually
checked against the manifest after the change; PDF hyphenation can remain.
Identical generated claims now merge their citation sources instead of repeating.

## Answer-quality findings

All 14 baseline requests returned HTTP 200. This is an availability result,
not an accuracy score. Review of displayed answers found these issues:

- `real-01` repeated the same self-attention claim four times. Exact duplicate
  claims now merge; a focused rerun no longer repeated that wording.
- `real-05` incorrectly described RAG-Sequence as retrieving entire document
  sequences and contradicted its own reported performance numbers. The focused
  rerun also failed: it invented a tokenization distinction. This remains open.
- `real-08` described dropout but omitted the expected representation-collapse
  explanation. `cross-01` discussed architectures without clearly explaining
  single-vector versus token-level representations in the baseline.
- Both fictional/unreported metric questions correctly returned insufficient
  evidence. That does not establish general hallucination resistance.

No overall answer-accuracy percentage is claimed. Report review fields remain
unset where claim-by-claim support has not been independently adjudicated.
Source IDs identify real retrieved chunks but do not prove a paraphrase is true.
The next quality work should target supported comparison answers and measure
them on additional independently labeled cases before changing the default model.

## Reproduce

Start Ollama with `qwen3:4b`, configure the normal local settings, then from the
repository root (PowerShell):

```powershell
$env:PYTHONPATH='backend'
backend/.venv/Scripts/python.exe scripts/evaluate_real_papers.py --download --label fresh-run
backend/.venv/Scripts/python.exe scripts/evaluate_real_papers.py --label fresh-retrieval --retrieval-only
backend/.venv/Scripts/python.exe scripts/evaluate_real_papers.py --label focused --case-id real-01 --case-id real-05 --case-id cross-01
```

Use a new label after parser/chunker changes: existing labels reuse the indexed
library, and parser code is not fingerprinted. Reports are written incrementally
to `reports/real-<label>.json`; rerunning a label replaces its report. Libraries
live under `data/real-evaluation/<label>/` and do not modify the app's library.
Model inference can take over a minute per question on this local CPU setup.
