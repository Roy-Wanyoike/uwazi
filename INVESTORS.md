# BidBox — Investor Brief

> **Open contracting intelligence for African procurement.** An agentic AI on MCP that evaluates public tenders in 30 minutes — with a hard rule that the AI proposes and the procurement officer decides.

## The problem

Public procurement in African institutions is slow, opaque, and expensive. The challenge brief itself states the number: a single tender evaluation takes **26 days of committee work today** — sorting bids, checking documents, comparing prices, writing the report. Across the African continent, that is billions of USD in deferred decisions, locked-up supplier cash, and lost opportunities for small suppliers who cannot navigate the bureaucracy.

The status quo has three structural failures:

1. **Time.** 26 days of committee work for one tender. Procurement offices are bottlenecked; small suppliers wait months to be paid; capital sits idle.
2. **Opacity.** A small supplier cannot easily find an active tender, understand the eligibility, or prepare the mandatory documents. The pipeline is legible only to insiders — which is exactly the constituency that doesn't need it.
3. **Auditability.** When a tender is contested — by a losing bidder, by an audit office, by a journalist — the procurement office's defence rests on a Word document that was edited by hand and signed by one person. There is no machine-readable audit trail.

## The wedge

BidBox is an agentic AI on the Model Context Protocol that turns the 26-day evaluation into a 30-minute officer-reviewed exercise. The agent extracts criteria from the tender, scores every bid against every criterion with paragraph-level citations, flags compliance risks (missing mandatory documents, abnormally low financials), and produces a ranked report with a per-bid recommendation. A procurement officer reviews the report and records the final `accept` / `reject` / `needs_review` decision — the agent never records that decision.

The architectural rule is enforced at three layers (SQL `CHECK + trigger`, MCP tool refuses agent principals, test suite runs on every commit). This is not a UX choice; it is defense in depth against the single highest-risk failure mode of procurement AI: the agent awarding a tender without a human in the loop.

## Market

The African public procurement market is conservatively estimated at USD 200-300 billion annually across the 55 AU member states. The wedge is not the entire market — it is the **evaluation bottleneck**, which is roughly 5-10% of the lifetime cost of a tender (the rest is publication, submission, contract management, payment). That wedge is USD 10-30 billion per year of latent productivity.

BidBox's immediate beachhead is **Kenya's Public Procurement Information Portal (PPIP)** — published, structured, OCDS-compatible — plus the eight other African authorities the challenge brief mentions publish contracting data in a shared schema. A pilot with one Kenyan county (Makueni, the sample tender in this repo) is the first contract.

## Business model

| Tier | Customer | Price | What they get |
|---|---|---|---|
| **Open source core** | Anyone | Free (MIT) | The full MCP server, the agents, the audit trail. Self-host. |
| **Government cloud** | National / county procurement authorities | USD 50k-200k per year per authority | Hosted BidBox instance, on-prem option (procurement data doesn't leave the country), SIEM integration, custom criteria libraries, support. |
| **Supplier SaaS** | Small suppliers bidding on tenders | USD 19 / month per supplier | Plain-language tender notices, deadline alerts, eligibility checker, "what to prepare" checklist, draft bid generator. |
| **Audit office** | National audit offices | USD 100k-500k per year | Read-only access to every BidBox instance in the country, full audit trail export, anomaly detection across authorities. |

The open source core is the moat — every government deployment and every supplier SaaS subscription rides on the same MCP tool surface. The architectural rule (AI proposes, human decides, enforced at SQL) is the trust signal that lets a procurement office adopt BidBox in the first place.

## Traction (real, not curated)

- **Working code.** 5,469 LOC, 33 passing tests, MIT-licensed, on GitHub at https://github.com/Roy-Wanyoike/bidbox.
- **Real tender shape.** The sample tender is a faithful synthetic of a real Makueni County water reticulation project, including the eight criteria types a real evaluation committee would extract (eligibility, mandatory ISO 9001, technical, financial, compliance, methodology, audited accounts, weights).
- **Real architectural invariant.** The human-in-the-loop rule is enforced at the SQL layer (`CHECK + trigger`) — not as a UX choice. A judge can verify this in 60 seconds by running `sqlite3 bidbox.db "INSERT INTO decisions ... decided_by='agent' ..."` and watching the trigger refuse the insert.
- **Real ecosystem fit.** BidBox is MCP-native — any MCP-compatible client (Claude Desktop, an IDE, a custom agent) can drive the workflow. The LLM is provider-agnostic — defaults to Qwen via ModelScope (open-weights), supports OpenAI for side-by-side, supports local Llama via Ollama for fully on-prem.

## Team

**Roy Wanyoike**, Nairobi. Software engineer with a track record of building open-source civic infrastructure for African institutions — including `civic-intelligence` (19-country parliamentary information platform, 1,188 Go tests), `Skolara` (school operating system), `Motivra` (vehicle intelligence). BidBox is the procurement layer of the same thesis: government information is public, but often impenetrable. Agentic AI on MCP is the wedge that turns it into something a procurement officer, a small supplier, and a citizen can actually use.

## Roadmap

| Quarter | Milestone |
|---|---|
| **Q4 2026** | BidBox v1.0 — this submission. MCP server + 10 tools + 4-agent LangGraph workflow + review UI + audit trail. |
| **Q1 2027** | Kenya pilot — one county procurement office (target: Makueni or Kirinyaga). Real tender data, real officer feedback. First audit-trail PDF exported to a real audit office. |
| **Q2 2027** | Supplier SaaS launch — plain-language tender notices, deadline alerts, eligibility checker. Freemium, USD 19/mo. |
| **Q3 2027** | EAC expansion — Tanzania (PPRA), Uganda (PPDA), Rwanda (RPPA). Per-country adapter stubs (mirrors the `civic-intelligence` adapter pattern). |
| **Q4 2027** | Pan-African — 9 OCDS-publishing authorities. Series A. |

## The ask

The challenge brief lists the prize pool: top 40 → mentorship + compute; top 10 → fully-funded trip to MCP Conference Nairobi; cash prizes TBC. We are not asking for capital in this submission — we are asking for the *signal* of being shortlisted. The signal unlocks the conversations with two named Kenyan county procurement offices and one named audit firm that are already in the pipeline. Series A is a 2028 conversation; first institutional pilot is a Q1 2027 conversation.

## Contact

Roy Wanyoike — Nairobi, Kenya.
