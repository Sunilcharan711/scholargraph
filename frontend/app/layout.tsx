import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { Suspense } from "react";
import WorkspaceNav from "./workspace-nav";
export const metadata: Metadata = { title: "ScholarGraph | Research workspace", description: "Explore papers. Follow the evidence." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><nav className="site-nav" aria-label="Main navigation">
    <Link className="wordmark" href="/">ScholarGraph</Link>
    <Suspense fallback={<span role="status">Loading workspace links…</span>}><WorkspaceNav/></Suspense>
    <Link href="/graph">Graph</Link><Link href="/evaluation">Evaluation</Link>
    </nav>{children}</body></html>;
}
