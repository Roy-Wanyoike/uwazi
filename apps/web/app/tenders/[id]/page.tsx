import Link from "next/link";
import { revalidatePath } from "next/cache";
import { evaluateTender, getTender, recordDecision, type BidEvaluation, type Decision, type TenderDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

function recClass(rec: string) {
  if (rec === "award") return "badge-award";
  if (rec === "shortlist") return "badge-shortlist";
  return "badge-reject";
}

function BidCard({ bid, rank, decisions, tenderId }: { bid: BidEvaluation; rank: number; decisions: Decision[]; tenderId: string }) {
  const myDecision = decisions.find((d) => d.bid_id === bid.bid_id);
  const widthPct = Math.min(100, (bid.weighted_score / 10) * 100);
  return (
    <div className="card bid-card" id={`bid-${bid.bid_id}`}>
      <h3>
        <span className="bid-rank">{rank}</span>
        {bid.bidder_name}
        <span className={`badge ${recClass(bid.recommendation)}`}>AI: {bid.recommendation}</span>
        {myDecision && (
          <span className={`badge ${recClass(myDecision.decision === "accept" ? "award" : myDecision.decision === "reject" ? "reject" : "shortlist")}`}>
            DECIDED: {myDecision.decision}
          </span>
        )}
      </h3>
      <div className="bid-meta">
        Total: {bid.total_score.toFixed(1)} · Weighted: <strong>{bid.weighted_score.toFixed(2)}/10</strong> ·
        {" "}{bid.risk_flags.length} risk flag{bid.risk_flags.length === 1 ? "" : "s"}
      </div>
      <div className="score-line">
        <div className="score-bar"><div style={{ width: `${widthPct}%` }} /></div>
        <strong>{bid.weighted_score.toFixed(1)}/10</strong>
      </div>
      <div className="bid-meta">{bid.recommendation_rationale}</div>

      {bid.risk_flags && bid.risk_flags.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="citation-label">Risk flags</div>
          {bid.risk_flags.map((r, i) => (
            <div key={i} className={`risk risk-${r.severity}`}>
              <strong>{r.risk_type}</strong> ({r.severity}): {r.description}
              <div className="citation">
                <div className="citation-label">Cited paragraph</div>
                {r.citation_paragraph}
              </div>
            </div>
          ))}
        </div>
      )}

      {bid.scores && bid.scores.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: "var(--accent)", fontSize: 13 }}>
            Show {bid.scores.length} score{bid.scores.length === 1 ? "" : "s"} with citations
          </summary>
          <div style={{ marginTop: 8 }}>
            {bid.scores.map((s, i) => (
              <div key={i} style={{ marginBottom: 12 }}>
                <strong>{s.score.toFixed(1)}/10</strong> — {s.rationale}
                <div className="citation">
                  <div className="citation-label">Tender criterion (cited)</div>
                  {s.citation_tender_paragraph}
                </div>
                <div className="citation">
                  <div className="citation-label">Bid response (cited)</div>
                  {s.citation_bid_paragraph}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {!myDecision && (
        <form className="decide-row" action={async (formData) => {
          "use server";
          const rationale = formData.get("rationale") as string;
          const decision = formData.get("decision") as "accept" | "reject" | "needs_review";
          if (!rationale || rationale.length < 10) {
            throw new Error("Rationale must be at least 10 chars.");
          }
          await recordDecision(tenderId, {
            bid_id: bid.bid_id,
            decision,
            rationale,
            principal_id: "officer-web",
            principal_kind: "human",
          });
          revalidatePath(`/tenders/${tenderId}`);
          revalidatePath(`/audit/${tenderId}`);
        }}>
          <input type="text" name="rationale" placeholder="Rationale (min 10 chars)…" required minLength={10} />
          <button type="submit" name="decision" value="accept" className="btn btn-ok">Accept</button>
          <button type="submit" name="decision" value="needs_review" className="btn btn-warn">Needs review</button>
          <button type="submit" name="decision" value="reject" className="btn btn-crit">Reject</button>
        </form>
      )}
    </div>
  );
}

export default async function TenderDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  // Defensive wrapper — any failure (network error, malformed response,
  // null body, missing fields) renders a friendly error card instead of
  // the generic Next.js "This page couldn't load" overlay.
  const errorCard = (msg: string) => (
    <div className="container" style={{ paddingTop: 32 }}>
      <div className="card" style={{ borderColor: "var(--crit)" }}>
        <h3 style={{ color: "var(--crit)", marginTop: 0 }}>Cannot reach the API</h3>
        <p className="bid-meta">{msg}</p>
        <p className="bid-meta" style={{ marginTop: 12 }}>
          Check the deployed Vercel URL, the FastAPI service status, and the
          <code> UWAZI_API_URL</code> binding env var. To verify directly:
        </p>
        <pre style={{ marginTop: 8 }}>{`curl https://<your-vercel-url>/api/v1/admin/seed-status
curl https://<your-vercel-url>/api/v1/tenders/${id}`}</pre>
      </div>
    </div>
  );

  let data: TenderDetail | undefined;
  try {
    data = await getTender(id);
  } catch (e) {
    return errorCard(e instanceof Error ? e.message : String(e));
  }

  // Validate shape — the API might return 200 with null/empty/partial body
  // (e.g., Neon cold-start timeout returns an empty body before FastAPI lifespan
  // finishes seeding). Render the friendly card instead of throwing.
  if (!data || !data.tender || !data.tender.title) {
    return errorCard(
      "API responded but the tender shape was unexpected. The Neon database " +
      "may still be cold-starting — wait 5 seconds and reload, or hit " +
      "/api/v1/admin/seed-status to verify the seed state."
    );
  }

  return (
    <div className="container" style={{ paddingTop: 32 }}>
      <div style={{ marginBottom: 16 }}>
        <Link href="/tenders" className="bid-meta" style={{ color: "var(--accent)" }}>← All tenders</Link>
      </div>

      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 28 }}>{data.tender.title}</h1>
        <div className="bid-meta">
          {data.tender.issuer} · {data.tender.country_code} · ingested {new Date(data.tender.ingested_at).toLocaleString()}
        </div>
      </header>

      <div className="rule-banner">
        <strong>Architectural rule:</strong> The agent has proposed. Record <code>accept</code> /{" "}
        <code>reject</code> / <code>needs_review</code> decisions below. The agent cannot record decisions — only you can.
      </div>

      {!data.report && data.bids.length > 0 && (
        <div className="card" style={{ marginBottom: 16, textAlign: "center" }}>
          <h3 style={{ marginTop: 0 }}>No evaluation yet</h3>
          <p className="bid-meta" style={{ marginBottom: 16 }}>{data.bids.length} bid{data.bids.length === 1 ? "" : "s"} ingested.</p>
          <form action={async () => {
            "use server";
            await evaluateTender(id);
            revalidatePath(`/tenders/${id}`);
            revalidatePath(`/audit/${id}`);
          }}>
            <button type="submit" className="btn btn-primary">Run agentic evaluation →</button>
          </form>
        </div>
      )}

      {data.report && (
        <>
          <div className="bid-meta" style={{ marginBottom: 16 }}>
            <span className="badge badge-ai">AI-GENERATED</span>
            {" "}
            Report generated {new Date(data.report.generated_at).toLocaleString()} ·{" "}
            {data.audit_count} audit entries ·{" "}
            <Link href={`/audit/${id}`} style={{ color: "var(--accent)" }}>View audit trail →</Link>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {data.report.bids.map((bid, i) => (
              <BidCard key={bid.bid_id} bid={bid} rank={i + 1} decisions={data.decisions} tenderId={id} />
            ))}
          </div>
        </>
      )}

      {data.bids.length === 0 && (
        <div className="empty">
          <h2>No bids yet</h2>
          <p>Ingest a bid first via the MCP tool <code>ingest_bid</code>.</p>
        </div>
      )}
    </div>
  );
}
