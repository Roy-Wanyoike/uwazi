import Link from "next/link";
import { getOpenNotices, type OpenNotice } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function NoticesPage() {
  let notices: OpenNotice[] = [];
  let note = "";
  let error: string | null = null;
  try {
    const data = await getOpenNotices("KE");
    notices = data.notices;
    note = data.note;
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="container" style={{ paddingTop: 32 }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 28 }}>Open Notices</h1>
        <p className="bid-meta">
          Every active tender in plain English — eligibility, mandatory documents, deadlines.
          For citizens and small suppliers. No legalese.
        </p>
      </header>

      <div className="rule-banner" style={{ background: "var(--accent-light)", borderColor: "var(--accent)", color: "var(--accent)" }}>
        Every claim on this page is <strong>FACT</strong> (not AI-generated). Sourced from the stored tender + criteria.
        AI explanations with citations are available via the <code>explain_tender_in_plain_language</code> MCP tool.
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--crit)" }}>
          <h3 style={{ color: "var(--crit)", marginTop: 0 }}>Cannot reach the API</h3>
          <p className="bid-meta">{error}</p>
        </div>
      )}

      {!error && notices.length === 0 && (
        <div className="empty">
          <h2>No active tenders yet</h2>
          <p>{note}</p>
          <p>Ingest a tender first: <code>python scripts/seed.py</code></p>
        </div>
      )}

      {notices.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {notices.map((n) => (
            <div key={n.tender_id} className="card">
              <h3 style={{ marginTop: 0, fontSize: 20 }}>{n.title}</h3>
              <div className="bid-meta">
                {n.issuer} · {n.country_code} · ingested {new Date(n.ingested_at).toLocaleString()} · {n.criteria_count} criteria
              </div>

              {n.eligibility_checklist.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="citation-label">Eligibility checklist</div>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {n.eligibility_checklist.map((c, i) => (
                      <li key={i} style={{ marginBottom: 6 }}>
                        <strong>{c.criterion}</strong> — {c.description}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {n.mandatory_documents.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="citation-label">Mandatory documents to prepare</div>
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {n.mandatory_documents.map((d, i) => (
                      <li key={i} style={{ marginBottom: 6 }}>
                        <strong>{d.document}</strong> — {d.description}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ marginTop: 16, padding: 12, background: "var(--bg-subtle)", borderRadius: 8, fontSize: 13 }}>
                <strong>Apply via:</strong> call the <code>ingest_bid</code> MCP tool with{" "}
                <code>tender_id={n.tender_id}</code> once you have prepared the mandatory documents.
                <div style={{ marginTop: 8 }}>
                  <Link href={`/tenders/${n.tender_id}`} className="btn btn-primary" style={{ padding: "4px 12px", fontSize: 12 }}>
                    View evaluation →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
