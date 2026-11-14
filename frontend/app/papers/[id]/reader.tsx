"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {api,type Paper} from "../../../lib/api";

type Detail=Paper & {metadata_json:{sections?:string[];keywords?:string[];page_count?:number};chunk_count:number;uploaded_at:string};
type Neighbors={nodes:{id:string;title:string}[];edges:{source_paper_id:string;target_paper_id:string;similarity_score:number}[]};
export default function Reader({id}:{id:string}) {
  const [paper,setPaper]=useState<Detail|null>(null),[related,setRelated]=useState<Neighbors|null>(null);
  const [error,setError]=useState(""),[graphError,setGraphError]=useState("");
  useEffect(()=>{
    const c=new AbortController();
    api<Detail>(`/papers/${id}?chunk_limit=1`,{signal:c.signal}).then(setPaper).catch(e=>{if(!c.signal.aborted)setError(e.message)});
    api<Neighbors>(`/graph/${id}`,{signal:c.signal}).then(setRelated).catch(e=>{if(!c.signal.aborted)setGraphError(e.message)});
    return ()=>c.abort();
  },[id]);
  return <main className="reading"><Link href="/library">← Library</Link>
    {error?<p role="alert">{error}</p>:!paper?<p role="status">Loading paper…</p>:<>
    <p className="eyebrow">PAPER RECORD · {paper.processing_status}</p><h1>{paper.title}</h1>
    <p>{paper.authors.join(", ") || "Authors unavailable"} · {paper.publication_year || "Year unavailable"}</p>
    <div className="actions">{paper.processing_status==="ready" && <><Link className="primary" href={`/chat?paper=${id}`}>Ask ScholarGraph</Link><a href={`/api/papers/${id}/pdf`} target="_blank" rel="noreferrer">Read PDF ↗</a><Link href={`/compare?paper=${id}`}>Compare</Link></>}</div>
    <div className="reading-card"><h2>Abstract</h2><p>{paper.abstract || "No abstract was extracted."}</p></div>
    <dl className="facts"><div><dt>File</dt><dd>{paper.filename}</dd></div><div><dt>Pages</dt><dd>{paper.metadata_json.page_count ?? "Unknown"}</dd></div><div><dt>Indexed passages</dt><dd>{paper.chunk_count}</dd></div><div><dt>Added</dt><dd>{new Date(paper.uploaded_at).toLocaleDateString()}</dd></div></dl>
    <h2>Sections</h2>{paper.metadata_json.sections?.length?<ol>{paper.metadata_json.sections.map(s=><li key={s}>{s}</li>)}</ol>:<p>No section headings were detected.</p>}
    <h2>Related papers</h2>{graphError?<p role="alert">{graphError}</p>:!related?<p>Loading related papers…</p>:!related.edges.length?<p>No related papers meet the current threshold.</p>:
      <ul>{related.edges.map(e=>{const other=e.source_paper_id===id?e.target_paper_id:e.source_paper_id;return <li key={other}><Link href={`/papers/${other}`}>{related.nodes.find(n=>n.id===other)?.title || "Related paper"}</Link> · {e.similarity_score.toFixed(3)}</li>})}</ul>}
    <Link href={`/graph?paper=${id}`}>Explore this neighborhood →</Link></>}
  </main>;
}
