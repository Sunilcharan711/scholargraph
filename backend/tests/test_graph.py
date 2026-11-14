from uuid import uuid4

from sqlalchemy import func, select

from app.models import Paper, PaperChunk, PaperRelationship


def seed(factory, specs):
    ids = []
    with factory() as session:
        for title, model, vectors in specs:
            p = Paper(
                title=title,
                authors=["Author"],
                publication_year=2021,
                filename="sample.pdf",
                file_path=uuid4().hex + ".pdf",
                metadata_json={"keywords": ["retrieval"]},
            )
            for i, v in enumerate(vectors):
                p.chunks.append(
                    PaperChunk(
                        page_number=1,
                        chunk_index=i,
                        text=title,
                        token_count=10,
                        embedding=v,
                        embedding_model=model if v else None,
                        embedding_dimensions=len(v) if v else None,
                    )
                )
            session.add(p)
            session.flush()
            ids.append(str(p.id))
        session.commit()
    return ids


def test_graph_scores_spaces_focus_and_refresh(client, session_factory):
    a, b, c, d, e = seed(
        session_factory,
        [
            ("mean", "v1", [[1, 0], [0, 1]]),
            ("x", "v1", [[1, 0]]),
            ("opposite", "v1", [[-1, 0]]),
            ("other model", "v2", [[1, 0]]),
            ("partial", "v1", [[1, 0], None]),
        ],
    )
    g = client.get("/api/graph").json()
    assert len(g["nodes"]) == 5 and len(g["edges"]) == 1
    edge = g["edges"][0]
    assert {edge["source_paper_id"], edge["target_paper_id"]} == {a, b}
    assert abs(edge["similarity_score"] - 2**-0.5) < 1e-6
    by_id = {n["id"]: n for n in g["nodes"]}
    assert not by_id[e]["indexed"] and by_id[a]["year"] == 2021
    assert by_id[a]["keywords"] == ["retrieval"]
    assert client.get("/api/graph?min_similarity=0.8").json()["edges"] == []
    assert {n["id"] for n in client.get("/api/graph/" + a).json()["nodes"]} == {a, b}
    assert len(client.get("/api/graph/" + c).json()["nodes"]) == 1
    assert client.get("/api/graph/" + str(uuid4())).status_code == 404
    for _ in range(2):
        assert client.post("/api/graph/rebuild").json()["edges"] == [edge]
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(PaperRelationship)) == 1
    assert client.delete("/api/papers/" + b).status_code == 204
    assert not client.get("/api/graph").json()["edges"]
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(PaperRelationship)) == 0


def test_graph_bounds_and_deterministic_ties(client, config, session_factory):
    config.graph_max_papers = 4
    config.graph_max_neighbors = 1
    ids = seed(session_factory, [(str(i), "v1", [[1, 0]]) for i in range(5)])
    g = client.get("/api/graph").json()
    assert g["truncated"] and len(g["edges"]) == 2
    ends = [e[k] for e in g["edges"] for k in ("source_paper_id", "target_paper_id")]
    assert len(set(ends)) == 4
    (older,) = set(ids) - {n["id"] for n in g["nodes"]}
    assert older in {n["id"] for n in client.get("/api/graph/" + older).json()["nodes"]}
    assert client.get("/api/graph").json() == g
    assert client.get("/api/graph?min_similarity=1.1").status_code == 422


def test_exact_matches_survive_threshold_and_overview_degree_cap(client, session_factory):
    *identical, different = seed(
        session_factory,
        [
            *((str(i), "same", [[1, 1]]) for i in range(7)),
            ("close, not identical", "same", [[1, 1.0001]]),
        ],
    )
    overview = client.get("/api/graph?min_similarity=1").json()
    assert len(overview["edges"]) == 15
    endpoints = {e[k] for e in overview["edges"] for k in ("source_paper_id", "target_paper_id")}
    assert different not in endpoints
    (isolated,) = set(identical) - endpoints
    focused = client.get(f"/api/graph/{isolated}?min_similarity=1").json()
    assert len(focused["edges"]) == 5
    assert all(
        e["similarity_score"] == 1 and isolated in (e["source_paper_id"], e["target_paper_id"])
        for e in focused["edges"]
    )
    assert different not in {n["id"] for n in focused["nodes"]}
