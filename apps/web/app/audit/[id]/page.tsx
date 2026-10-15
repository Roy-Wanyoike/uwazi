import Link from "next/link";
import { getAuditTrail, type AuditTrail } from "@/lib/api";

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
        The complete trail is available here and through the structured audit API.
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
            {trail.ai_proposals.length === 0 ? (
              <div className="empty"><p>No AI proposals or tool calls recorded yet.</p></div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {trail.ai_proposals.map((entry) => (
                  <div key={entry.id} className="card" style={{ padding: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                      <strong><span className="badge badge-ai">{entry.entry_kind.replace("_", " ").toUpperCase()}</span> {entry.actor}</strong>
                      <span className="bid-meta">{new Date(entry.timestamp).toLocaleString()}</span>
                    </div>
                    <pre style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(entry.payload, null, 2)}</pre>
                  </div>
                ))}
              </div>
            )}
            <p className="bid-meta" style={{ marginTop: 12 }}>{trail.note}</p>
          </section>
        </>
      )}
    </div>
  );
}
