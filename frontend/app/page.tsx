import Link from "next/link";
import {Card,CardHeader,CardTitle,CardDescription} from "../components/ui/card";
const features=[
  ["01 / Discover","Search the literature","Find passages by keyword, meaning, or both.","/search"],
  ["02 / Verify","Ask your papers","Read a cited answer and open the exact PDF page.","/chat"],
  ["03 / Connect","Compare and explore","Compare methods and findings, then follow related research.","/compare"],
];
export default function Home(){
 return <main className="welcome"><section className="hero"><p className="eyebrow">SCHOLARGRAPH · RESEARCH WORKSPACE</p>
 <h1>Understand research,<br/><span>not just search it.</span></h1>
 <p className="intro">Bring your PDFs together. Compare what the papers report and follow each answer back to the evidence.</p>
 <div className="actions"><Link className="primary" href="/library#upload">Add research papers →</Link><Link href="/library">Open library</Link></div></section>
 <section className="grid gap-4 md:grid-cols-3" aria-label="Explore ScholarGraph">{features.map(([tag,title,body,url])=><Card key={tag} className="feature"><CardHeader><small className="eyebrow">{tag}</small><CardTitle><Link href={url}>{title} →</Link></CardTitle><CardDescription>{body}</CardDescription></CardHeader></Card>)}</section></main>;
}
