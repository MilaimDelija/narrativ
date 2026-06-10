/**
 * NARRATIV API client — full typed interface
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Request types ─────────────────────────────────────────────────────────

export interface PostIn {
  post_id: string;
  account_id: string;
  timestamp: string;           // ISO-8601
  text: string;
  hashtags?: string[];
  amplifies_account?: string;
  is_sponsored?: boolean;
}

export interface AccountIn {
  account_id: string;
  created_at: string;          // ISO-8601
  followers: number;
  following: number;
  has_default_avatar?: boolean;
  display_name?: string;
  handle?: string;
}

export interface AnalyzeRequest {
  posts: PostIn[];
  accounts: AccountIn[];
  topic?: string;
  tlp?: string;
  review_threshold?: number;
  min_active_signals?: number;
}

// ── Response types ────────────────────────────────────────────────────────

export interface AnchorProof {
  report_id: string;
  report_hash: string;
  anchored_at: string;
  on_chain: boolean;
  tx_hash: string | null;
  block_number: number | null;
  contract_address: string;
  network: string;
  pending_reason?: string;
}

export interface FullAnalysisResponse {
  report_id: string;
  cib: Record<string, unknown>;
  narrative_tracker: Record<string, unknown>;
  dashboard: Record<string, unknown>;
  prebunking: Record<string, unknown>;
  anchor: AnchorProof;
}

// ── API calls ─────────────────────────────────────────────────────────────

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const msg = await r.text().catch(() => r.statusText);
    throw new Error(`API ${r.status}: ${msg}`);
  }
  return r.json();
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`API ${r.status}: ${r.statusText}`);
  return r.json();
}

/** Raw CIB engine report */
export const analyzeCIB = (req: AnalyzeRequest) =>
  post<Record<string, unknown>>("/analyze", req);

/** CIB + dashboard payload */
export const getDashboard = (req: AnalyzeRequest) =>
  post<Record<string, unknown>>("/dashboard", req);

/** Full pipeline: CIB + Narrative Tracker + Prebunking + Blockchain */
export const fullAnalysis = (req: AnalyzeRequest) =>
  post<FullAnalysisResponse>("/full", req);

/** Pre-computed demo run (no input needed) */
export const getDemo = () =>
  get<Record<string, unknown>>("/demo");

/** List stored reports */
export const listReports = (limit = 20, topic?: string) => {
  const q = topic ? `?limit=${limit}&topic=${encodeURIComponent(topic)}` : `?limit=${limit}`;
  return get<Record<string, unknown>[]>(`/reports${q}`);
};

/** Get a stored report by ID */
export const getReport = (reportId: string) =>
  get<Record<string, unknown>>(`/reports/${reportId}`);

/** Health check */
export const health = () =>
  get<{ status: string; version: string; db_connected: boolean }>("/");
