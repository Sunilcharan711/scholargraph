"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, Answer, Citation, Paper, Source } from "../lib/api";
type View = "search" | "ask";
type Evidence = { title: string; paper_id: string; page: number; section: string | null; snippet: string };
export default function Workspace() {
  const [papers, setPapers] = useState<Paper[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]), [view, setView] = useState<View>("search");
  const [mode, setMode] = useState("hybrid"), [query, setQuery] = useState("");
  const [results, setResults] = useState<Source[]>([]), [answer, setAnswer] = useState<Answer | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null), [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false), [loading, setLoading] = useState(true);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [ran, setRan] = useState(false);
  const [latency, setLatency] = useState(0), [storage, setStorage] = useState("Connecting");
  const [provider, setProvider] = useState(""), [deleting, setDeleting] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (evidence) dialog.current?.showModal(); }, [evidence]);
  const fileInput = useRef<HTMLInputElement>(null);
  const load = useCallback(async () => {
    setLoading(true);
    try { const data = await api<{items: Paper[]; total: number}>(`/papers?limit=20&offset=${offset}`); setPapers(data.items); setTotal(data.total); }
    catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { api<{storage: string; answer_model: string | null}>("/status").then(s => { setStorage(s.storage); setProvider(s.answer_model || ""); }).catch(() => setStorage("Backend offline")); }, []);
  function clearResult() { setRan(false); setResults([]); setAnswer(null); setEvidence(null); }
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true); setError(""); setNotice("");
    let count = 0;
    try { for (const file of Array.from(files)) { const form = new FormData(); form.append("file", file); await api<Paper>("/papers/upload", {method: "POST", body: form}); count++; } }
    catch (e) { setError((e as Error).message); }
    finally { setNotice(`${count} paper${count === 1 ? "" : "s"} added.`); setUploading(false); if (fileInput.current) fileInput.current.value = ""; await load(); clearResult(); }
  }
  async function remove(paper: Paper) {
    if (!window.confirm(`Delete “${paper.title}” and its indexed chunks?`)) return;
    setDeleting(paper.id); setError("");
    try { await api(`/papers/${paper.id}`, {method: "DELETE"}); setSelected(ids => ids.filter(id => id !== paper.id)); clearResult(); await load(); }
    catch (e) { setError((e as Error).message); } finally { setDeleting(null); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!query.trim() || busy) return;
    setBusy(true); setError(""); clearResult();
    try {
      const body = {paper_ids: selected, mode, top_k: 6};
      if (view === "search") { const data = await api<{results: Source[]; latency_ms: number}>("/search", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, query})}); setResults(data.results); setLatency(data.latency_ms); }
      else { const data = await api<Answer>("/chat/query", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, question: query})}); setAnswer(data); setLatency(data.latency_ms); }
      setRan(true);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function openCitation(c: Citation) { setEvidence({...c, title: c.paper_title}); }
  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-mark">⌘</span> ScholarGraph<span className="beta">LAB</span></a>
      <div className="workspace-label">PERSONAL WORKSPACE</div>
      <div className="nav-active"><span>▧</span> Paper library <span className="count">{total}</span></div>
      <div className="library-heading"><span>YOUR PAPERS</span><button onClick={() => void load()} disabled={loading} aria-label="Refresh library">↻</button></div>
      <p className="small muted">Select papers to narrow your search.</p>
      <div className="paper-list" aria-label="Paper library">
        {loading ? <p className="muted small">Loading library…</p> : papers.length ? papers.map(p => <div className="paper-row" key={p.id}>
          <label><input type="checkbox" checked={selected.includes(p.id)} disabled={busy || p.processing_status !== "ready"} onChange={() => { setSelected(ids => ids.includes(p.id) ? ids.filter(id => id !== p.id) : [...ids, p.id]); clearResult(); }}/><span>{p.title}<small>{p.processing_status === "ready" ? (p.authors.join(", ") || p.filename) : "Deletion pending"}</small></span></label>
          <button className="delete" title={`Delete ${p.title}`} aria-label={`Delete ${p.title}`} disabled={!!deleting || busy} onClick={() => void remove(p)}>×</button>
        </div>) : <div className="library-empty">Your reading list starts here.<br/>Upload a PDF to add a paper.</div>}
      </div>
      {total > 20 && <div className="pagination"><button disabled={offset === 0 || loading} onClick={() => setOffset(n => Math.max(0,n-20))}>Previous</button><span>{offset+1}–{Math.min(offset+20,total)}</span><button disabled={offset+20 >= total || loading} onClick={() => setOffset(n => n+20)}>Next</button></div>}
      {selected.length > 0 && <button className="clear-filter" disabled={busy} onClick={() => {setSelected([]); clearResult();}}>Clear {selected.length} selected</button>}
      <label className={`upload ${uploading ? "disabled" : ""}`}><span>＋</span><strong>{uploading ? "Reading & indexing…" : "Add research papers"}</strong><small>{uploading ? "First use may download the embedding model" : "Choose PDFs · indexed locally"}</small><input ref={fileInput} type="file" accept="application/pdf,.pdf" multiple disabled={uploading || busy} onChange={e => void upload(e.target.files)}/></label>
      <div className="sidebar-footer"><span className="avatar">SC</span><span>Sunil charan<small>Research workspace</small></span></div>
    </aside>
    <main>
      <header><div><span className="muted">Workspace</span><span className="slash">/</span> Research desk</div><span className="status"><i/>{storage === "sqlite-demo" ? "Local demo · SQLite" : storage === "postgresql" ? "PostgreSQL" : storage}</span></header>
      <div className="content">
        <div className="eyebrow">FOLLOW YOUR CURIOSITY. CHECK THE EVIDENCE.</div>
        <h1>Your papers.<br/><span>A clearer perspective.</span></h1>
        <p className="intro">Search across your research and ask questions with<br className="desktop-break"/> every answer connected to its source.</p>
        <div className="tabs" role="tablist" aria-label="Research mode">{(["search", "ask"] as View[]).map(v => <button role="tab" aria-selected={view===v} disabled={busy} className={view===v ? "active" : ""} key={v} onClick={() => {setView(v); clearResult(); setError("");}}>{v === "search" ? "⌕  Search papers" : "✧  Ask your library"}</button>)}</div>
        <form className="query-box" onSubmit={submit}>
          <label className="sr-only" htmlFor="question">{view === "search" ? "Search query" : "Research question"}</label>
          <textarea id="question" value={query} disabled={busy} maxLength={2000} onChange={e => setQuery(e.target.value)} placeholder={view === "search" ? "Find a method, idea, or exact phrase…" : "What do these papers say about…?"} rows={2}/>
          <div className="query-toolbar"><div><label htmlFor="retrieval" className="sr-only">Retrieval mode</label><select id="retrieval" value={mode} disabled={busy} onChange={e => {setMode(e.target.value); clearResult();}}><option value="hybrid">Hybrid search</option><option value="dense">Semantic search</option><option value="bm25">Keyword search</option></select><span className="scope">{selected.length ? `${selected.length} selected` : "All papers"}</span></div><button className="primary" disabled={busy || uploading || !query.trim()}>{busy ? "Working…" : view === "search" ? "Search ↗" : "Ask question ↗"}</button></div>
        </form>
        <div className="under-query"><span>{view === "search" ? "Hybrid blends keyword matches with semantic meaning." : provider ? `Answer model: ${provider} · Verify claims against sources.` : "Configure a local answer model to enable generated answers."}</span><span>PRIVATE WORKSPACE</span></div>
        {error && <div className="alert" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <section className="results" aria-live="polite" aria-busy={busy}>
          {busy ? <div className="empty"><div className="orb">⌕</div><h2>{view === "ask" ? "Reading the evidence…" : "Searching your papers…"}</h2><p>Local models may take a moment to warm up.</p></div> : ran ? <>
            <div className="result-heading"><h2>{view === "search" ? `${results.length} passages found` : "Grounded answer"}</h2><span>{(latency/1000).toFixed(2)}s · {mode}</span></div>
            {answer && <article className="answer"><span className="answer-label">{answer.insufficient_evidence ? "MORE EVIDENCE NEEDED" : "FROM YOUR LIBRARY"}</span><p>{answer.answer}</p><div className="citations">{answer.citations.map(c => <button key={c.source} onClick={() => openCitation(c)}>[{c.source}] {c.paper_title} · p. {c.page}</button>)}</div></article>}
            {view === "search" && (results.length ? results.map((r,i) => <button className="result-card" key={r.chunk_id} onClick={() => setEvidence(r)}><div className="result-meta"><span>PASSAGE {String(i+1).padStart(2,"0")}</span><span>{r.score_type.toUpperCase()} {r.score.toFixed(4)}</span></div><h3>{r.title}</h3><p>{r.snippet}</p><footer><span>Page {r.page}{r.section ? ` · ${r.section}` : ""}</span><span>View evidence ↗</span></footer></button>) : <div className="empty"><h2>No matching passages</h2><p>Try different terms, select more papers, or upload a PDF.</p></div>)}
          </> : <div className="empty"><div className="orb">▧</div><h2>{total ? "An idea worth exploring?" : "Make room for your next discovery."}</h2><p>{total ? "Search a concept or ask a question about your library." : "Add a few papers, then explore the ideas that connect them."}</p><div className="steps"><span><b>01</b> Add papers</span><span><b>02</b> Explore ideas</span><span><b>03</b> Trace the evidence</span></div></div>}
        </section>
        <footer className="page-footer">Built for thoughtful research.<span>ScholarGraph · Sunil charan</span></footer>
      </div>
    </main>
    {evidence && <dialog ref={dialog} className="evidence-overlay" aria-label="Source evidence" onCancel={() => setEvidence(null)} onClick={e => { if (e.target === e.currentTarget) setEvidence(null); }}><section className="evidence-panel" onClick={e => e.stopPropagation()} onKeyDown={e => {if(e.key === "Escape") setEvidence(null);}}><button autoFocus className="close" aria-label="Close evidence" onClick={() => setEvidence(null)}>×</button><div className="eyebrow">SOURCE EVIDENCE</div><h2>{evidence.title}</h2><p className="muted">Page {evidence.page}{evidence.section ? ` · ${evidence.section}` : ""}</p><blockquote>{evidence.snippet}</blockquote><a className="primary pdf-link" href={`/api/papers/${evidence.paper_id}/pdf#page=${evidence.page}`} target="_blank" rel="noreferrer">Open original PDF ↗</a><p className="small muted">Citations identify retrieved passages. Always check whether the source supports the claim.</p></section></dialog>}
  </div>;
}
