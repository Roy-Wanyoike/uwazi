import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>
            Evidence-first tender review<br />for African procurement teams.
          </h1>
          <p className="lead">
            Uwazi turns tender and bid documents into a cited review pack designed for a roughly
            20-minute committee review. <strong>The AI proposes</strong>;{" "}
            <strong>the procurement committee decides</strong>. Enforced at the SQL layer.
          </p>
          <div className="cta">
            <Link href="/tenders" className="btn btn-primary">View tenders →</Link>
            <Link href="/notices" className="btn">Open Notices (citizens)</Link>
            <a
              href="https://github.com/Roy-Wanyoike/uwazi"
              target="_blank"
              rel="noreferrer"
              className="btn"
            >
              GitHub ↗
            </a>
          </div>
        </div>
      </section>

      <section className="container" style={{ paddingTop: 48 }}>
        <div className="rule-banner">
          <strong>Architectural rule:</strong> The agent may propose scores, risk flags, and recommendations.
          The agent may <strong>never</strong> record a decision. Enforced at three layers — SQL{" "}
          <code>CHECK</code> + trigger, the MCP tool refuses agent principals, and focused tests cover both layers.
        </div>

        <div className="stats">
          <div className="stat">
            <div className="num">10</div>
            <div className="label">MCP tools</div>
          </div>
          <div className="stat">
            <div className="num">5</div>
            <div className="label">LangGraph nodes</div>
          </div>
          <div className="stat">
            <div className="num">42</div>
            <div className="label">Tests passing</div>
          </div>
          <div className="stat">
            <div className="num">26d → ~20m</div>
            <div className="label">Target review time</div>
          </div>
          <div className="stat">
            <div className="num">MIT</div>
            <div className="label">License</div>
          </div>
        </div>

        <div className="grid grid-3" style={{ marginTop: 32 }}>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>🛠️ Your own MCP server</h3>
            <p className="bid-meta">
              Ten tools — ingest, evaluate, decide. Every tool is independently reusable; a stranger can call{" "}
              <code>list_tenders</code> from any MCP client without invoking the rest.
            </p>
          </div>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>🔌 One MCP server you didn&apos;t write</h3>
            <p className="bid-meta">
              The official <code>mcp-server-fetch</code> handles HTTP redirects, gzip, charset, robots.txt,
              SSRF protection. ~500 LOC saved; any upstream improvement lands without our PR.
            </p>
          </div>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>🧭 Open-source orchestration</h3>
            <p className="bid-meta">
              LangGraph <code>StateGraph</code> with 5 nodes + 1 conditional edge. The agent plans,
              calls tools, recovers from failure. Not a one-model-call loop.
            </p>
          </div>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>🦙 Open-weights model</h3>
            <p className="bid-meta">
              Default: <strong>Qwen2.5-72B-Instruct</strong> via ModelScope. Also supports local Llama
              via Ollama for fully on-prem — procurement data often cannot leave the country.
            </p>
          </div>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>🔍 Sourced findings</h3>
            <p className="bid-meta">
              Every score, every risk flag, every recommendation cites a specific paragraph in the source
              documents. The citation validator performs 5 checks and fails closed.
            </p>
          </div>
          <div className="card card-hover">
            <h3 style={{ marginTop: 0 }}>📜 Defensible audit trail</h3>
            <p className="bid-meta">
              Every AI proposal and every human decision is timestamped, attributed, and stamped
              <code>actor_kind=human</code> or <code>agent</code>, and available through the audit API and UI.
            </p>
          </div>
        </div>

        <div style={{ marginTop: 48, padding: 24, background: "var(--bg-subtle)", borderRadius: 12 }}>
          <h3 style={{ marginTop: 0 }}>Run it in one command</h3>
          <pre style={{ margin: 0 }}>
{`git clone https://github.com/Roy-Wanyoike/uwazi.git
cd uwazi
./run-demo.sh    # venv + install + seed + evaluate + UI`}
          </pre>
          <p className="bid-meta" style={{ marginTop: 16 }}>
            Or read the{" "}
            <a href="https://github.com/Roy-Wanyoike/uwazi/blob/main/README.md" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>
              README
            </a>{" "}
            for the long version.
          </p>
        </div>
      </section>
    </>
  );
}
