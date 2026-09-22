export type Paper = { id: string; title: string; authors: string[]; filename: string; processing_status: string; abstract: string | null };
export type Source = { paper_id: string; title: string; chunk_id: string; page: number; section: string | null; snippet: string; score: number; score_type: string };
export type Citation = { source: number; paper_id: string; paper_title: string; chunk_id: string; page: number; section: string | null; snippet: string; relevance_score: number };
export type Answer = { answer: string; citations: Citation[]; insufficient_evidence: boolean; latency_ms: number; model: string | null };
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `Request failed (${response.status}). Check that the backend is running.`;
    try { const body = await response.json(); if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((e: {msg: string}) => e.msg).join("; "); } catch {}
    throw new Error(detail);
  }
  return response.status === 204 ? undefined as T : response.json();
}
