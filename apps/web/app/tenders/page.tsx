import Link from "next/link";
import { listTenders, type TenderSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TendersPage() {
  let tenders: TenderSummary[] = [];
  let error: string | null = null;
  try {
    const data = await listTenders();
    tenders = data.tenders;
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="container" style={{ paddingTop: 32 }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 28 }}>Tenders</h1>
        <p className="bid-meta">Every tender ingested into Uwazi. Click one to view the ranked evaluation.</p>
      </header>

      {error && (
        <div className="card" style={{ borderColor: "var(--crit)" }}>
          <h3 style={{ marginTop: 0, color: "var(--crit)" }}>Cannot reach the API</h3>
          <p className="bid-meta">{error}</p>
          <p className="bid-meta">Make sure the FastAPI backend is running: <code>python -m uwazi.cli serve</code></p>
        </div>
      )}

      {!error && tenders.length === 0 && (
        <div className="empty">
          <h2>No tenders yet</h2>
          <p>Seed the sample:</p>
          <pre>{`python scripts/seed.py`}</pre>
        </div>
      )}

      {tenders.length > 0 && (
        <div className="grid grid-2">
          {tenders.map((t) => (
            <Link key={t.id} href={`/tenders/${t.id}`} className="card card-hover">
              <h3 style={{ marginTop: 0 }}>{t.title}</h3>
              <div className="bid-meta">
                {t.issuer} · {t.country_code} · {t.bid_count} bid{t.bid_count === 1 ? "" : "s"}
              </div>
              <div className="bid-meta">Ingested {new Date(t.ingested_at).toLocaleString()}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
