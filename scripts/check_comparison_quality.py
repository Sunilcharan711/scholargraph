"""Verify the methods-only and explicit-negative cases with configured local models."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from app.core.config import Settings
from app.db.demo import demo_engine
from app.main import create_app
from fastapi.testclient import TestClient
from make_demo_papers import generate
from sqlalchemy.orm import sessionmaker


def main():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = Settings(upload_dir=root / "uploads", embedding_local_files_only=True)
        engine = demo_engine(root / "comparison.db")
        try:
            with TestClient(create_app(config, sessionmaker(engine))) as client:
                ids = []
                for path in generate(root / "papers")[::2]:
                    response = client.post(
                        "/api/papers/upload", files={"file": (path.name, path.read_bytes())}
                    )
                    response.raise_for_status()
                    ids.append(response.json()["id"])
                for topic in ("methodology", "findings"):
                    result = client.post(
                        "/api/compare", json={"paper_ids": ids, "dimension": topic}
                    )
                    result.raise_for_status()
                    cells = result.json()["cells"]
                    for i, cell in enumerate(cells):
                        assert cell["paper_id"] == ids[i] and not cell["error"], cell
                        answer = cell["answer"]
                        print(topic, cell["title"], answer["answer"], flush=True)
                        if topic == "findings" and i == 0:
                            assert answer["insufficient_evidence"] and not answer["citations"]
                            continue
                        assert not answer["insufficient_evidence"]
                        pages = {c["page"] for c in answer["citations"]}
                        assert pages == ({2} if topic == "methodology" else {3}), pages
                        assert all(c["paper_id"] == ids[i] for c in answer["citations"])
                        text = answer["answer"].lower()
                        if topic == "findings":
                            assert "no measured yield improvement" in text
                        elif i == 0:
                            assert "retrieval" in text or "rank" in text
                        else:
                            assert "moisture" in text or "irrigation" in text
                ids = []
                for title, text in [
                    (
                        "Threshold protocol",
                        "An accuracy of 95% was specified as the acceptance threshold. "
                        "No experiments have been run.",
                    ),
                    (
                        "Measurement study",
                        "Unlike previous studies, our model achieved 95% accuracy "
                        "on the held-out dataset.",
                    ),
                    (
                        "Threshold adjustment",
                        "When the threshold was lowered, "
                        "measured recall increased from 60% to 72%.",
                    ),
                ]:
                    with pymupdf.open() as pdf:
                        pdf.new_page().insert_textbox((50, 60, 550, 600), text)
                        pdf.set_metadata({"title": title})
                        upload = client.post(
                            "/api/papers/upload", files={"file": ("study.pdf", pdf.tobytes())}
                        )
                        upload.raise_for_status()
                        ids.append(upload.json()["id"])
                result = client.post(
                    "/api/compare", json={"paper_ids": ids, "dimension": "findings"}
                )
                result.raise_for_status()
                target, measured, adjustment = result.json()["cells"]
                assert not target["error"] and not measured["error"]
                assert (
                    target["answer"]["insufficient_evidence"] and not target["answer"]["citations"]
                )
                assert "achieved 95% accuracy" in measured["answer"]["answer"], measured
                assert {c["paper_id"] for c in measured["answer"]["citations"]} == {ids[1]}
                assert not adjustment["error"]
                assert "increased from 60% to 72%" in adjustment["answer"]["answer"], adjustment
                assert {c["paper_id"] for c in adjustment["answer"]["citations"]} == {ids[2]}
                print("Acceptance threshold excluded; held-out measurement cited.", flush=True)
                sentence = "Our measured accuracy increased to 92%."
                with pymupdf.open() as pdf:
                    pdf.new_page().insert_text((50, 60), sentence)
                    pdf.new_page().insert_text(
                        (50, 60), "Instrument maintenance logs are available."
                    )
                    upload = client.post(
                        "/api/papers/upload", files={"file": ("short.pdf", pdf.tobytes())}
                    )
                upload.raise_for_status()
                paper = upload.json()
                answer = client.post(
                    "/api/chat/query",
                    json={
                        "paper_ids": [paper["id"]],
                        "mode": "bm25",
                        "question": "What accuracy is reported?",
                    },
                )
                answer.raise_for_status()
                body = answer.json()
                assert "92%" in body["answer"] and not body["insufficient_evidence"], body
                assert any(
                    c["paper_id"] == paper["id"] and c["page"] == 1 and c["snippet"] == sentence
                    for c in body["citations"]
                )
                print("Two-page paper: 92% accuracy cited on page 1.", flush=True)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
