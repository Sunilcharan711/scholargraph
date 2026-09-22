"""Generate original, clearly synthetic PDFs for a reproducible demonstration."""

from pathlib import Path

import pymupdf
from app.core.config import PROJECT_ROOT

PAPERS = [
    (
        "Hybrid Retrieval in a Small Library",
        [
            (
                "Abstract",
                (
                    "SYNTHETIC DEMO PAPER. This is an original illustrative "
                    "document, not published research. We explore combining "
                    "keyword and semantic retrieval in a small research library."
                ),
            ),
            (
                "Methods",
                (
                    "The prototype combines BM25 keyword retrieval with dense "
                    "sentence embeddings using reciprocal rank fusion. RRF "
                    "combines one-based ranks rather than adding incompatible raw "
                    "scores. The fusion constant is 60. BM25 preserves exact "
                    "identifiers such as ALPHA-42."
                ),
            ),
            (
                "Limitations",
                (
                    "The experiment uses only three synthetic documents. It "
                    "cannot establish performance on real scientific literature. "
                    "Dense embeddings can miss rare exact identifiers, and "
                    "lexical search can miss paraphrases. Larger corpora require "
                    "a separate recall and latency evaluation."
                ),
            ),
        ],
    ),
    (
        "Traceable Evidence for Research Answers",
        [
            (
                "Abstract",
                (
                    "SYNTHETIC DEMO PAPER. This original illustrative document "
                    "describes provenance in research question answering. It is "
                    "not a real publication."
                ),
            ),
            (
                "Methods",
                (
                    "Each retrieved passage retains its paper identifier, chunk "
                    "identifier, page number, and section heading. The language "
                    "model selects integer source IDs. The application maps those "
                    "IDs to stored metadata and rejects unknown sources. Every "
                    "answer claim must include a source."
                ),
            ),
            (
                "Limitations",
                (
                    "A valid citation identifier does not establish that a "
                    "passage supports the claim. Readers must inspect the "
                    "original evidence. Prompt injection in uploaded text remains "
                    "a risk. If the retrieved evidence cannot answer a question, "
                    "the model should explicitly abstain."
                ),
            ),
        ],
    ),
    (
        "Water Use in Greenhouse Tomatoes",
        [
            (
                "Abstract",
                (
                    "SYNTHETIC DEMO PAPER. This original illustrative document "
                    "describes an imaginary greenhouse study. It is not published "
                    "research or agricultural guidance."
                ),
            ),
            (
                "Methods",
                (
                    "The imaginary study measures soil moisture in greenhouse "
                    "tomato beds. Drip irrigation supplies water directly to "
                    "plant roots. Sensors record soil moisture each morning. "
                    "Mulch reduces evaporation from the soil surface."
                ),
            ),
            (
                "Limitations",
                (
                    "This demonstration reports no measured yield improvement and "
                    "no validated water savings. Weather, soil type, and "
                    "greenhouse conditions would affect outcomes in a real trial."
                ),
            ),
        ],
    ),
]


def generate(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, (title, sections) in enumerate(PAPERS, 1):
        path = directory / f"demo-{index}.pdf"
        with pymupdf.open() as document:
            for heading, text in sections:
                page = document.new_page()
                page.insert_textbox((50, 45, 545, 120), title, fontsize=19)
                page.insert_text((50, 155), heading, fontsize=16)
                page.insert_textbox((50, 185, 545, 690), text, fontsize=12)
                page.insert_text(
                    (50, 780),
                    "ScholarGraph / original synthetic demo / not published research",
                    fontsize=9,
                )
            document.set_metadata({"title": title, "author": "ScholarGraph synthetic demo"})
            document.save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for path in generate(PROJECT_ROOT / "data/sample-papers"):
        print(path)
