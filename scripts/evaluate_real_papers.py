"""Reproducible real-PDF development evaluation in an isolated local library."""

import argparse
import hashlib
import json
import re
import time

import httpx
from app.core.config import PROJECT_ROOT, Settings
from app.db.demo import demo_engine
from app.main import create_app
from fastapi.testclient import TestClient
from run_rag_eval import Recorder
from sqlalchemy.orm import sessionmaker


def normalized(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--case-id", action="append", help="Run selected cases after a focused fix")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.label):
        parser.error("Use a simple label containing letters, digits, underscores or hyphens.")
    manifest = json.loads((PROJECT_ROOT / "evaluation/real-papers.json").read_text())
    pdf_root = PROJECT_ROOT / "data/real-papers"
    pdf_root.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with httpx.Client(timeout=90, follow_redirects=True, trust_env=False) as download:
        for paper in manifest["papers"]:
            path = pdf_root / (paper["id"] + ".pdf")
            if not path.exists() and args.download:
                response = download.get(paper["pdf_url"])
                response.raise_for_status()
                if not response.content.startswith(b"%PDF-"):
                    raise ValueError(f"Not a PDF: {paper['id']}")
                path.write_bytes(response.content)
                time.sleep(3)
            hashes[paper["id"]] = hashlib.sha256(path.read_bytes()).hexdigest()
            if paper.get("sha256") and hashes[paper["id"]] != paper["sha256"]:
                raise ValueError(f"PDF checksum changed: {paper['id']}")
    root = PROJECT_ROOT / "data/real-evaluation" / args.label
    root.mkdir(parents=True, exist_ok=True)
    report_path = PROJECT_ROOT / "reports" / f"real-{args.label}.json"
    report_path.parent.mkdir(exist_ok=True)
    config = Settings(database_url="", upload_dir=root / "uploads")
    engine = demo_engine(root / "library.db")
    try:
        with TestClient(create_app(config, sessionmaker(engine))) as client:
            identity = client.app.state.embedder.spec.key
            state_path = root / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if state and (state["hashes"] != hashes or state["embedding_model"] != identity):
                raise ValueError("Inputs/model changed; choose a new label for an isolated run.")
            ids = state.get("ids", {})
            for paper in manifest["papers"]:
                if paper["id"] in ids:
                    continue
                path = pdf_root / (paper["id"] + ".pdf")
                response = client.post(
                    "/api/papers/upload", files={"file": (path.name, path.read_bytes())}
                )
                response.raise_for_status()
                ids[paper["id"]] = response.json()["id"]
                state_path.write_text(
                    json.dumps(
                        {
                            "hashes": hashes,
                            "embedding_model": identity,
                            "ids": ids,
                        }
                    ),
                    encoding="utf-8",
                )
                print("Indexed", paper["id"], response.json()["title"], flush=True)
            report = {
                "model": config.chat_model,
                "embedding_model": identity,
                "hashes": hashes,
                "cases": [],
            }
            for case in manifest["cases"]:
                if args.case_id and case["id"] not in args.case_id:
                    continue
                row = {**case, "retrieval": {}}
                expected = {ids[p] for p in case["paper_ids"]}
                for mode in ("dense", "bm25", "hybrid"):
                    response = client.post(
                        "/api/search",
                        json={
                            "query": case["question"],
                            "mode": mode,
                            "top_k": 5,
                        },
                    )
                    response.raise_for_status()
                    hits = response.json()["results"]
                    row["retrieval"][mode] = {
                        "paper_recall_at_5": len(expected & {h["paper_id"] for h in hits})
                        / len(expected)
                        if not case["expected_abstention"]
                        else None,
                        "hits": hits,
                    }
                if not args.retrieval_only:
                    recorder = Recorder(client.app.state.answer_provider)
                    client.app.state.answer_provider = recorder
                    try:
                        response = client.post(
                            "/api/chat/query",
                            json={
                                "question": case["question"],
                                "paper_ids": [ids[p] for p in case["paper_ids"]],
                                "top_k": 6,
                            },
                        )
                    finally:
                        client.app.state.answer_provider = recorder.provider
                    row["status"] = response.status_code
                    row["response"] = response.json()
                    row["context"] = recorder.context
                    row["claims"] = recorder.claims
                    row["review"] = {
                        "answers_question": None,
                        "all_claims_supported": None,
                        "expected_point_coverage": [None] * len(case["expected_points"]),
                        "notes": "Requires human review of answer and supplied passages.",
                    }
                report["cases"].append(row)
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(case["id"], row.get("status", "retrieval only"), flush=True)
            print(report_path)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
