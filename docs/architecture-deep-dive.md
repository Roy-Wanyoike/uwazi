# Architecture

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

This document is the canonical architectural contract for Uwazi. Every design decision in the codebase traces back to one of the rules below.

## 1. The four hard rules

1. **Evidence before AI.** Every score, every risk flag, every recommendation must cite at least one paragraph from the source documents (tender + bid). A response that cannot be grounded in evidence fails the citation validator and is not published.
2. **AI proposes, the officer decides.** The agent writes only to the `proposals`, `scores`, `risk_flags`, and `reports` tables. The `decisions` table has a `CHECK (decided_by <> 'agent')` constraint plus a SQL trigger that refuses any agent-originated insert.
3. **Never fabricate.** The agent may never invent a criterion, a bid response, a score, or a citation. If the LLM produces a citation that does not match a supplied paragraph, the citation is stripped and the claim is dropped.
4. **Audit everything.** Every AI output carries `ai_generated=True`, a `correlation_id`, a token-cost stamp, and a list of citations. Every human decision carries the officer's principal ID, a timestamp, and a rationale.

## 2. The agentic workflow

```
Tender PDF/MD
    ↓
ingest_tender → ExtractorAgent → criteria[] (with citations)
    ↓
Bid PDF/MD × N
    ↓
ingest_bid × N
    ↓
evaluate_bids(tender_id)
    ↓
    ┌────────────────── OrchestratorAgent ──────────────────┐
    │  For each bid:                                        │
    │    BidAnalyzerAgent → responses[] (with citations)    │
    │    ScorerAgent       → scores[] (with citations)       │
    │    RiskAgent         → risk_flags[] (with citations)    │
    │  Compose ranked report + recommendation per bid       │
    └────────────────────────────────────────────────────────┘
    ↓
report (immutable, stamped ai_generated=True)
    ↓
Procurement officer reviews → record_officer_decision
    ↓
audit_trail (AI proposals + human decisions)
```

The orchestrator is an MCP client. Every step in the workflow is an MCP tool call. This means:
- The agent is a thin orchestrator; the heavy lifting is in the tools.
- Any MCP-compatible client can drive the same workflow.
- The human-in-the-loop boundary is enforced at the tool layer.

## 3. The MCP tool surface

| Tool | What it does | Who can call |
|---|---|---|
| `list_tenders` | Lists all ingested tenders. | Any MCP client. |
| `ingest_tender` | Parses tender PDF/MD → extracts criteria with citations. | Any MCP client. |
| `ingest_bid` | Parses bid PDF/MD → stores against a tender. | Any MCP client. |
| `evaluate_bids` | Runs the orchestrator workflow. Returns a ranked report. | Any MCP client. |
| `get_report` | Fetches the full evaluation report (citations, scores, risk flags). | Any MCP client. |
| `record_officer_decision` | Officer records `accept` / `reject` / `needs-review`. **Human-only.** | Requires a human principal (`principal.kind='human'`). The tool refuses requests where `principal.kind='agent'`. |
| `get_audit_trail` | Full audit trail of AI proposals + human decisions. | Any MCP client. |

## 4. The citation validator

Every AI output passes through the citation validator before it is persisted. The validator performs five checks:

1. **Existence** — does the cited document exist in the uwazi store?
2. **Pointer correctness** — does the citation point to a paragraph that actually exists in that document?
3. **Span support** — does the cited paragraph actually contain the claim being made? (Embedding similarity ≥ 0.75 — configurable.)
4. **Claim strength** — is the claim stronger than the evidence supports? (Heuristic: if the claim uses "must", "shall", "always", but the evidence uses "may", "should", "sometimes" — the claim is too strong.)
5. **Source authority** — is the cited source authoritative for this claim type? (Tender passages are authoritative for criteria; bid passages are authoritative for responses.)

If any check fails, the claim is not published. The agent surfaces a `[This score could not be fully verified against the source documents]` marker instead.

## 5. The human-in-the-loop boundary

This is the single most important architectural decision in Uwazi. It is enforced at three layers:

### Schema level

The `decisions` table:

```sql
CREATE TABLE decisions (
    id            TEXT PRIMARY KEY,
    tender_id     TEXT NOT NULL REFERENCES tenders(id),
    bid_id        TEXT NOT NULL REFERENCES bids(id),
    decision      TEXT NOT NULL CHECK (decision IN ('accept','reject','needs_review')),
    rationale     TEXT NOT NULL,
    decided_by    TEXT NOT NULL,
    decided_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (decided_by <> 'agent')
);

CREATE TRIGGER decisions_no_agent_writer
BEFORE INSERT ON decisions
FOR EACH ROW
WHEN NEW.decided_by = 'agent'
BEGIN
    SELECT RAISE(ABORT, 'agent may not record decisions');
END;
```

### Code level

The Python agent service has no direct DB credentials on the `decisions` table. It calls the MCP tool `record_officer_decision`, which validates the principal and writes through the FastAPI layer (which itself goes through the SQL trigger).

### Process level

The test suite includes `tests/test_human_in_the_loop.py`, which verifies that agent principals cannot insert into `decisions` through either the MCP tool or the database boundary.

## 6. Storage

SQLite by default. The schema is portable to Postgres with no code changes — only the connection string differs.

Tables:
- `tenders` — tender documents + extracted criteria
- `bids` — bid documents against a tender
- `documents` — the parsed text + paragraph index of every tender and bid (so citations can be resolved)
- `criteria` — extracted evaluation criteria (with citations to tender paragraphs)
- `responses` — extracted bid responses per criterion (with citations to bid paragraphs)
- `scores` — per (bid, criterion) score (with citations)
- `risk_flags` — per-bid risk flags (with citations)
- `reports` — composed evaluation reports (immutable, stamped `ai_generated=True`)
- `decisions` — officer decisions (the human-only table)

## 7. ADRs

Architectural decisions are recorded inline as ADRs in this document. When a decision needs context that does not fit in a bullet, it gets its own ADR file under `docs/adr/`.

- **ADR-0001 — AI cannot record decisions.** Enforced at schema + code + process levels. See §5.
- **ADR-0002 — Citations are paragraph-level, not page-level.** This makes the citation system work for both PDFs (which have pages) and Markdown (which doesn't). A citation is `(document_id, paragraph_index)`.
- **ADR-0003 — SQLite first, Postgres-ready.** Zero-config for the demo; portable for production.
- **ADR-0004 — MCP-native.** Every capability is an MCP tool. The agent is an MCP client. No private internal API.

## 8. Why MCP

The challenge brief says: *"Build an agentic AI, using MCP, plus open-source tools."* MCP is not a checkbox — it is the architectural choice that makes the human-in-the-loop boundary enforceable. By putting every capability behind an MCP tool, we get:

1. **A single permission surface.** The `record_officer_decision` tool can refuse requests where `principal.kind='agent'`. There is no back door.
2. **Provider-agnostic LLM.** Any MCP-compatible client can drive the workflow. We are not locked to a single LLM vendor.
3. **Composable.** A procurement office can mount Uwazi's MCP server alongside their existing tools (file system, calendar, email) and let a higher-level agent compose across them.

## 9. What is explicitly out of scope

- **Bid submission portal.** Uwazi evaluates bids; it does not receive them. Bids arrive as documents (PDF or Markdown) via `ingest_bid`.
- **Payment integration.** Not part of the evaluation workflow.
- **Multi-tenant.** Uwazi is single-tenant per deployment. A procurement office runs their own instance.
- **Appeals workflow.** A losing bidder's appeal is a separate process that Uwazi does not implement; the structured audit trail can inform a future appeal workflow.
