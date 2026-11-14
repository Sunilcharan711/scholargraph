"use client";

import { useState } from "react";
import { api, Answer, Citation } from "../lib/api";

const dimensions = {
  objective: "Research objective", methodology: "Methodology", dataset: "Dataset",
  architecture: "Model architecture", evaluation: "Evaluation", findings: "Findings",
  limitations: "Limitations", future_work: "Future work",
};
type Dimension = keyof typeof dimensions;
type Row = {
  dimension: Dimension;
  question: string;
  cells: {paper_id: string; title: string; answer: Answer | null; error: string | null}[];
};

export default function Comparison({ids, busy, setBusy, openCitation}: {
  ids: string[]; busy: boolean; setBusy: (busy: boolean) => void; openCitation: (c: Citation) => void;
}) {
  const [dimension, setDimension] = useState<Dimension>("methodology");
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  async function compare() {
    setError(""); setBusy(true);
    try {
      const row = await api<Row>("/compare", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({paper_ids: ids, dimension})});
      setRows(previous => [...previous.filter(r => r.dimension !== dimension), row]);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <section aria-label="Paper comparison">
    <h2>Compare papers</h2>
    <p>Select 2–4 papers from the library, then choose what to compare. Each answer cites only its own paper.</p>
    <div className="compare-controls"><label>Comparison topic <select disabled={busy} value={dimension}
      onChange={event => setDimension(event.target.value as Dimension)}>
      {Object.entries(dimensions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
    </select></label>
    <button className="primary" disabled={busy || ids.length < 2 || ids.length > 4}
      onClick={() => void compare()}>{busy ? "Reading papers…" : "Compare selected papers"}</button></div>
    <p role="status" className="muted small">{ids.length} selected{ids.length > 4 ? " · Remove papers to compare up to four." : ""}</p>
    {error && <p className="alert" role="alert">{error}</p>}
    {rows.length > 0 && <div className="comparison-scroll" tabIndex={0} aria-label="Comparison results"><table>
      <caption>Evidence by paper and topic</caption>
      <thead><tr><th scope="col">Topic</th>{rows[0].cells.map(c => <th scope="col" key={c.paper_id}>{c.title}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.dimension}><th scope="row">{dimensions[row.dimension]}</th>
        {row.cells.map(cell => <td key={cell.paper_id}>{cell.error ? <p role="alert">{cell.error}</p> :
          <><p>{cell.answer?.answer}</p><div className="citations">{cell.answer?.citations.map(c =>
            <button key={c.source} onClick={() => openCitation(c)}>[{c.source}] Page {c.page}</button>)}</div></>}
        </td>)}</tr>)}</tbody></table></div>}
  </section>;
}
