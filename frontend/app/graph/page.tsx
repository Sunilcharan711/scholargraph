"use client";

import Network from "./network";
import Link from "next/link";
import {useSearchParams} from "next/navigation";
import {Suspense, useEffect, useState} from "react";
import {api} from "../../lib/api";

type Paper = {id:string; title:string; authors:string[]; year:number|null; keywords:string[]; indexed:boolean};
type Edge = {source_paper_id:string; target_paper_id:string; similarity_score:number};
type Graph = {nodes:Paper[]; edges:Edge[]; min_similarity:number; truncated:boolean; papers_considered:number};

export default function GraphPage() {
  return <Suspense fallback={<p role="status">Loading graph…</p>}><Explorer/></Suspense>;
}

function Explorer() {
  const requested = useSearchParams().get("paper");
  const [graph,setGraph] = useState<Graph|null>(null);
  const [detail,setDetail] = useState<{id:string;data?:Graph;error?:string}|null>(null);
  const focus = requested || graph?.edges[0]?.source_paper_id || graph?.nodes[0]?.id || "";
  function setFocus(id:string) { window.history.pushState(null,"",`/graph?paper=${encodeURIComponent(id)}`); }
  const [showSemantic,setShowSemantic] = useState(true);
  const [minimum,setMinimum] = useState(0);
  const [error,setError] = useState("");
  const [revision,reload] = useState(0);
  useEffect(()=>{
    const controller = new AbortController();
    api<Graph>("/graph",{signal:controller.signal}).then(g=>{
      if(controller.signal.aborted) return;
      setGraph(g); setMinimum(g.min_similarity);
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
    return ()=>controller.abort();
  },[revision]);
  useEffect(()=>{
    if(!focus) return;
    const controller = new AbortController();
    api<Graph>(`/graph/${encodeURIComponent(focus)}`,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setDetail({id:focus,data});})
      .catch(e=>{if(!controller.signal.aborted)setDetail({id:focus,error:e.message});});
    return ()=>controller.abort();
  },[focus,revision]);
  const neighborhood = detail?.id===focus ? detail.data : undefined;
  const problem = error || (detail?.id===focus && detail.error);
  const paper = neighborhood?.nodes.find(n=>n.id===focus);
  const options = [...(graph?.nodes || [])];
  if(paper && !options.some(p=>p.id===paper.id)) options.push(paper);
  const neighbors = (neighborhood?.edges || []).filter(e=>showSemantic && e.similarity_score>=minimum &&
    (e.source_paper_id===focus || e.target_paper_id===focus)).map(e=>({
      paper:neighborhood!.nodes.find(n=>n.id===(e.source_paper_id===focus?e.target_paper_id:e.source_paper_id))!,
      score:e.similarity_score,
    }));
  return <main className="graph-page"><header><Link href="/library">← Library</Link><span>ScholarGraph</span></header>
    <section className="content"><div className="eyebrow">RELATED PAPERS</div><h1>Scholar Graph</h1>
    <p>Explore papers that discuss similar topics. A link shows content similarity, not a citation.</p>
    {problem?<div role="alert">{problem} <button onClick={()=>{setError("");setDetail(null);reload(n=>n+1)}}>Try again</button></div>:
    !graph || (focus && !neighborhood)?<p role="status">Loading graph…</p>:!paper?<p>No papers yet. <Link href="/library#upload">Add a PDF to your library.</Link></p>:<>
    {graph.truncated && <p>The picker lists the {graph.papers_considered} most recent ready papers. Open any other paper’s graph from the research desk.</p>}
    <div className="compare-controls"><label>Explore a paper <select value={focus} onChange={e=>setFocus(e.target.value)}>
    {options.map(n=><option key={n.id} value={n.id}>{n.title}</option>)}</select></label>
    <label><input type="checkbox" checked={showSemantic} onChange={e=>setShowSemantic(e.target.checked)}/> Semantic similarity links</label>
    <label>Minimum similarity: {minimum.toFixed(2)} <input type="range" min={graph.min_similarity} max="1" step="0.01" value={minimum}
      onChange={e=>setMinimum(Number(e.target.value))}/></label></div>
    <h2>{paper.title}</h2>
    <p>{[paper.authors.join(", "),paper.year,paper.keywords.join(" · ")].filter(Boolean).join(" · ")}</p>
    <a className="pdf-link" href={`/api/papers/${paper.id}/pdf`} target="_blank" rel="noreferrer">Open original PDF ↗</a>
    <h3>Related papers ({neighbors.length})</h3>
    {!neighbors.length?<p>{!paper.indexed?"This paper needs compatible indexed passages before it can be linked.":showSemantic?"No links meet this similarity threshold.":"Semantic similarity links are hidden."}</p>:<>
    <Network paper={paper} neighbors={neighbors} onFocus={setFocus}/>
    <ol>{neighbors.map(({paper:n,score})=><li key={n.id}><button aria-label={`Explore ${n.title}`} onClick={()=>setFocus(n.id)}>{n.title}</button> · {score.toFixed(3)}</li>)}</ol></>}
    </>}</section></main>;
}
