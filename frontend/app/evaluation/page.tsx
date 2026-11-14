import baseline from "./baseline.json";
import {Card,CardHeader,CardTitle,CardDescription} from "../../components/ui/card";

export default function Evaluation() {
 const q=baseline.generation;
 return <main className="reading"><p className="eyebrow">EVALUATION · RECORDED BASELINE</p>
 <h1>How the workspace performed</h1><p>Recorded local checks on three synthetic papers. These are historical measurements, not scores for your current library.</p>
 <h2>Passage retrieval</h2><p>{baseline.queries} authored queries. A hit means the expected paper appeared within the cutoff.</p>
 <div className="comparison-scroll"><table><caption>Retrieval results by method</caption><thead><tr>{["Method","Hit @ 1","Hit @ 5","MRR @ 5","Mean latency"].map(s=><th key={s} scope="col">{s}</th>)}</tr></thead>
 <tbody>{Object.entries(baseline.retrieval).map(([mode,r])=><tr key={mode}><th scope="row">{mode}</th><td>{(100*r.hit_at_1).toFixed(1)}%</td><td>{(100*r.hit_at_5).toFixed(1)}%</td><td>{r.mrr_at_5.toFixed(3)}</td><td>{r.mean_ms.toFixed(1)} ms</td></tr>)}</tbody></table></div>
 <h2>Generated answers</h2><p>Six questions answered using {baseline.chat_model}.</p>
 <div className="grid gap-4 md:grid-cols-2">{[
   ["Source integrity",q.source_integrity_passes,"Each checked source mapped to its stored passage and page."],
   ["Answer or abstain",q.abstention_decisions_matching_expectation,"The model answered or abstained as expected. This does not measure factual accuracy."],
 ].map(([label,value,description])=><Card className="feature" key={label}><CardHeader><small>{label}</small><CardTitle>{value} / {q.cases}</CardTitle><CardDescription>{description}</CardDescription></CardHeader></Card>)}</div>
 <details><summary>Measurement notes</summary><p>The queries were written alongside the corpus. Timings exclude initial model loading. A valid source ID does not prove a claim is supported.</p><p>Embedding model: {baseline.embedding_model}</p><p>Sources: demo-evaluation.json and qa-evidence-first.json.</p></details></main>;
}
