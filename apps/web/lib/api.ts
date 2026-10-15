/**
 * API client for the Uwazi backend.
 *
 * Two execution contexts:
 *
 * 1. Server-side (Next.js Server Components / Server Actions / Route Handlers).
 *    `window` is undefined; relative URLs fail with
 *    "Failed to parse URL from /api/v1/...". Use the absolute URL.
 *
 *    Priority order:
 *      a) process.env.UWAZI_API_URL — the Vercel services binding env var.
 *         This is the internal URL of the `api` service as injected by
 *         Vercel into the `web` service's runtime.
 *      b) process.env.VERCEL_URL — Vercel's auto-injected deployment URL.
 *         Build an absolute URL from this; the vercel.json rewrites will
 *         route /api/v1/* to the api service.
 *      c) http://localhost:8000 — local dev fallback.
 *
 * 2. Client-side (browser fetches).
 *    `window` exists; relative URLs are resolved by the browser.
 *    Vercel's vercel.json `rewrites` routes /api/v1/* to the api service.
 */

function getBaseURL(): string {
  // Server-side: absolute URL from the binding env var.
  if (typeof window === "undefined") {
    // (a) Vercel services binding — preferred.
    const bound = process.env.UWAZI_API_URL;
    if (bound && bound.length > 0) {
      return `${bound.replace(/\/$/, "")}/api/v1`;
    }
    // (b) VERCEL_URL fallback — works when the binding isn't injected
    // (e.g., older Vercel project, or binding misconfigured). Uses the
    // vercel.json rewrite to route /api/v1/* to the api service.
    if (process.env.VERCEL_URL) {
      return `https://${process.env.VERCEL_URL}/api/v1`;
    }
    // (c) Local dev fallback.
    return "http://localhost:8000/api/v1";
  }
  // Client-side: relative URL. Vercel's vercel.json rewrites route to api service.
  return "/api/v1";
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getBaseURL()}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error ?? err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TenderSummary {
  id: string;
  title: string;
  issuer: string;
  country_code: string;
  ingested_at: string;
  bid_count: number;
}

export interface Score {
  score: number;
  rationale: string;
  citation_tender_paragraph: string;
  citation_bid_paragraph: string;
}

export interface RiskFlag {
  risk_type: string;
  severity: "info" | "warning" | "critical";
  description: string;
  citation_paragraph: string;
}

export interface BidEvaluation {
  bid_id: string;
  bidder_name: string;
  total_score: number;
  weighted_score: number;
  recommendation: "award" | "shortlist" | "reject";
  recommendation_rationale: string;
  scores: Score[];
  risk_flags: RiskFlag[];
}

export interface Decision {
  id: string;
  bid_id: string;
  decision: "accept" | "reject" | "needs_review";
  decided_by: string;
  decided_at: string;
  rationale: string;
}

export interface TenderDetail {
  tender: {
    id: string;
    title: string;
    issuer: string;
    country_code: string;
    ingested_at: string;
  };
  bids: { id: string; bidder_name: string; ingested_at: string }[];
  report: {
    id: string;
    tender_id: string;
    generated_at: string;
    ai_generated: boolean;
    bids: BidEvaluation[];
  } | null;
  decisions: Decision[];
  audit_count: number;
}

export interface AuditEntry {
  id: string;
  tender_id: string;
  bid_id: string | null;
  entry_kind: "ai_proposal" | "tool_call";
  actor: string;
  actor_kind: "agent";
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface AuditTrail {
  tender_id: string;
  ai_proposals: AuditEntry[];
  human_decisions: Decision[];
  note: string;
}

export interface OpenNotice {
  tender_id: string;
  title: string;
  issuer: string;
  country_code: string;
  ingested_at: string;
  criteria_count: number;
  eligibility_checklist: { criterion: string; description: string }[];
  mandatory_documents: { document: string; description: string }[];
  apply_via: string;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const listTenders = () => api<{ tenders: TenderSummary[] }>("/tenders");

export const getTender = (id: string) =>
  api<TenderDetail>(`/tenders/${encodeURIComponent(id)}`);

export const getAuditTrail = (id: string) =>
  api<AuditTrail>(`/tenders/${encodeURIComponent(id)}/audit`);

export const evaluateTender = (id: string) =>
  api<{ report_id: string; bids_evaluated: number; criteria_extracted: number }>(
    "/evaluate",
    { method: "POST", body: JSON.stringify({ tender_id: id }) },
  );

export const recordDecision = (
  tenderId: string,
  body: { bid_id: string; decision: "accept" | "reject" | "needs_review"; rationale: string; principal_id?: string; principal_kind?: "human" | "agent" },
) =>
  api<{
    decision_id: string;
    tender_id: string;
    bid_id: string;
    decision: string;
    decided_by: string;
    decided_at: string;
  }>(`/tenders/${encodeURIComponent(tenderId)}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getOpenNotices = (countryCode: string = "KE") =>
  api<{ country_code: string; notices: OpenNotice[]; note: string }>(
    `/open_notices?country_code=${encodeURIComponent(countryCode)}`,
  );
