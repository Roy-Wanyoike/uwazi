import Link from "next/link";

interface AuditEntry {
  id: string;
  tender_id: string;
  bid_id: string | null;
  entry_kind: "ai_proposal" | "human_decision" | "tool_call";
  actor: string;
  actor_kind: "human" | "agent";
  payload: Record<string, unknown>;
  timestamp: string;
}

interface Decision {
  id: string;
  bid_id: string;
  decision: "accept" | "reject" | "needs_review";
  decided_by: string;
  decided_at: string;
  rationale: string;
}

interface AuditTrail {
  tender_id: string;
  ai_proposals: AuditEntry[];
  human_decisions: Decision[];
  note: string;
}

async function getAuditTrail(tenderId: string): Promise<AuditTrail> {
  // The audit trail endpoint is currently on the MCP server, not FastAPI.
  // For now, the web UI shows the decisions stored via FastAPI.
  // To see the full audit trail (incl. AI proposals), call:
  //   python -m uwazi.cli audit --tender-id <id>
  // Use the absolute URL on the server (UWAZI_API_URL binding on Vercel,
  // or VERCEL_URL fallback, or localhost in dev).
  const bound = process.env.UWAZI_API_URL;
  const host =
    typeof window === "undefined"
      ? bound
        ? `${bound.replace(/\/$/, "")}/api/v1`
        : process.env.VERCEL_URL
        ? `https://${process.env.VERCEL_URL}/api/v1`
        : "http://localhost:8000/api/v1"
      : "/api/v1";
  const res = await fetch(`${host}/tenders/${tenderId}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return {
    tender_id: tenderId,
    ai_proposals: [],
    human_decisions: data.decisions ?? [],
    note: "AI proposals are queryable via the MCP `get_audit_trail` tool. Run `python -m uwazi.cli audit --tender-id <id>` to see them.",
  };
}

export default async function AuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let trail: AuditTrail | null = null;
  let error: string | null = null;
  try {
    trail = await getAuditTrail(id);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="container" style={{ paddingTop: 32 }}>
      <div style={{ marginBottom: 16 }}>
        <Link href={`/tenders/${id}`} className="bid-meta" style={{ color: "var(--accent)" }}>← Back to tender</Link>
      </div>

      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 28 }}>Audit trail</h1>
        <p className="bid-meta">Tender: <code>{id}</code> · every AI proposal + every human decision, timestamped and attributed.</p>
      </header>

      <div className="rule-banner">
        Every entry below is stamped <code>actor_kind=human</code> or <code>actor_kind=agent</code>.
        The audit trail is exportable as a signed PDF for the procurement archive.
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--crit)" }}>
          <h3 style={{ color: "var(--crit)", marginTop: 0 }}>Cannot load audit trail</h3>
          <p className="bid-meta">{error}</p>
        </div>
      )}

      {trail && (
        <>
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>
              Human decisions ({trail.human_decisions.length})
            </h2>
            {trail.human_decisions.length === 0 ? (
              <div className="empty">
                <p>No decisions recorded yet. Visit the tender page to record one.</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {trail.human_decisions.map((d) => (
                  <div key={d.id} className="card" style={{ padding: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                      <strong>
                        <span className="badge badge-ai">DECISION</span>{" "}
                        {d.decision.toUpperCase()}
                      </strong>
                      <span className="bid-meta">{new Date(d.decided_at).toLocaleString()}</span>
                    </div>
                    <div className="bid-meta" style={{ marginTop: 8 }}>
                      Bid: <code>{d.bid_id}</code> · by <strong>{d.decided_by}</strong> (human)
                    </div>
                    <div style={{ marginTop: 8 }}>{d.rationale}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>
              AI proposals ({trail.ai_proposals.length})
            </h2>
            <div className="card" style={{ padding: 16 }}>
              <p className="bid-meta">{trail.note}</p>
              <pre style={{ marginTop: 12 }}>{`python -m uwazi.cli audit --tender-id ${id}`}</pre>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
