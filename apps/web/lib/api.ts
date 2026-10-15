/**
 * API client for the BidBox backend.
 *
 * On Vercel: BIDBOX_API_URL is injected via the `services` binding
 * (see vercel.json — the `web` service binds to the `api` service).
 * On local dev: falls back to http://localhost:8000 (FastAPI dev).
 * The next.config.mjs rewrites /api/* to BIDBOX_API_URL so the browser
 * can call the same path on either environment.
 */

const BASE = "/api/v1";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error ?? `HTTP ${res.status}`);
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

export const getTender = (id: string) => api<TenderDetail>(`/tenders/${id}`);

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
  }>(`/tenders/${tenderId}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getOpenNotices = (countryCode: string = "KE") =>
  api<{ country_code: string; notices: OpenNotice[]; note: string }>(
    `/open_notices?country_code=${countryCode}`,
  ).catch(() => {
    // If the FastAPI backend isn't running, return an empty list with a note.
    return {
      country_code: countryCode,
      notices: [],
      note: "Run `python -m bidbox.cli serve` to start the API, then refresh.",
    };
  });
