/**
 * NARRATIV API client
 * Typed wrappers around the FastAPI backend.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AnalyzeRequest {
  posts: PostIn[];
  accounts: AccountIn[];
  topic?: string;
  tlp?: string;
  review_threshold?: number;
  min_active_signals?: number;
}

export interface PostIn {
  post_id: string;
  account_id: string;
  timestamp: string;
  text: string;
  hashtags?: string[];
  amplifies_account?: string;
  is_sponsored?: boolean;
}

export interface AccountIn {
  account_id: string;
  created_at: string;
  followers: number;
  following: number;
  has_default_avatar?: boolean;
  display_name?: string;
  handle?: string;
}

export async function analyzeRaw(req: AnalyzeRequest) {
  const r = await fetch(`${BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

export async function getDashboard(req: AnalyzeRequest) {
  const r = await fetch(`${BASE}/dashboard`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`API error ${r.status}`);
  return r.json();
}

export async function getDemo() {
  const r = await fetch(`${BASE}/demo`);
  if (!r.ok) throw new Error(`Demo endpoint error ${r.status}`);
  return r.json();
}
