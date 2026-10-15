# ARCHITECTURE — Uwazi (one page)

> Required by the challenge brief: *"ARCHITECTURE.md — one page. Agent shape, MCP servers built versus borrowed, and why."*

## Agent shape

Uwazi is a LangGraph state machine with 5 nodes and 4 conditional edges. The agent plans, calls tools, recovers from failure, and stops at a hard human-in-the-loop gate.

```
                    ┌──────────────────────────────────────────┐
                    │           UWAZI LANGGRAPH GRAPH          │
                    └──────────────────────────────────────────┘

START → extract_criteria → analyze_bids → score_bids → flag_risks → compose_report → END
            │                  │              │             │              │
            └── (no criteria) ──────────────────────────────→ compose_report

Nodes (each is an async function of state):
  extract_criteria  ExtractorAgent     over tender paragraphs (LLM call)
  analyze_bids      BidAnalyzerAgent   per bid (LLM call)
  score_bids        ScorerAgent        per (bid, criterion) pair (LLM call)
  flag_risks        RiskAgent          per bid (LLM call)
  compose_report    OrchestratorAgent  pure Python (no LLM)
```

State is a single `TypedDict` (`UwaziState`) that flows through every node. Each node returns a partial dict that LangGraph merges. The graph is compiled with `MemorySaver` checkpointer — an interrupted evaluation can be resumed from the last checkpoint (not yet wired into the UI; see *what's unfinished* in the README).

**Recovery path:** if `extract_criteria` returns an empty list (the LLM found no criteria), the conditional edge skips `analyze_bids → score_bids → flag_risks` and jumps to `compose_report`, which produces a report with `errors=["extractor: no criteria"]` rather than crashing. Per-bid failures in `analyze_bids` / `score_bids` / `flag_risks` are caught, logged to `state["errors"]`, and the bid is short-circuited — the rest of the bids continue.

## MCP servers built vs borrowed

| MCP server | Source | Why |
|---|---|---|
| **Uwazi MCP server** (`src/uwazi/mcp_server.py`) | **Built.** FastMCP on stdio. 10 tools: `list_tenders`, `fetch_tender_notice`, `ingest_tender`, `ingest_bid`, `evaluate_bids`, `get_report`, `open_notices`, `explain_tender_in_plain_language`, `record_officer_decision` (HUMAN-ONLY), `get_audit_trail`. | The challenge requires our own server with ≥3 tools; this is the protocol surface for the entire workflow. |
| **Official MCP fetch server** (`mcp-server-fetch`) | **Borrowed.** Anthropic / MCP maintainers. | Handles HTTP redirects, gzip, charset detection, HTML stripping, robots.txt respect, and SSRF protection — features that would take ~500 LOC to reproduce. Used by `fetch_tender_notice` to pull tender notices from public procurement portals. Any upstream improvement lands in our agent without a single PR. |

**Orchestration:** LangGraph (open-source, Apache 2.0). Why: it is the de-facto open-source orchestrator for agent workflows with named-tool calls. Strangers reading the code recognise the shape. It supports conditional edges, recovery paths, and human-in-the-loop interrupts.

**LLM gateway:** Provider-agnostic, OpenAI-compatible. Default is **Qwen2.5-72B-Instruct via ModelScope** (open-weights model, satisfies the brief). Falls back to STUB mode (deterministic canned responses) for offline demos and tests. Also supports local Llama via Ollama for fully on-prem deployments — important because procurement data often cannot leave the country.

## The human-in-the-loop gate

The single most important architectural rule:

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

Enforced at three layers:

1. **SQL** — `CHECK (decided_by <> 'agent')` constraint + `BEFORE INSERT` trigger on `decisions`. Verified by `tests/test_human_in_the_loop.py::test_sql_trigger_refuses_agent_writer`.
2. **MCP tool** — `record_officer_decision` refuses any request where `principal_kind='agent'`. Verified by `tests/test_human_in_the_loop.py::test_tool_refuses_agent_principal`.
3. **Verification** — focused tests exercise both the tool-layer refusal and the database constraint.

## Citations

Every AI output (score, risk flag, plain-language summary) carries `ai_generated=True` and a list of citations. Citations are paragraph-level `(document_id, paragraph_index)`, not page-level — this makes the system work for both PDFs (which have pages) and Markdown (which doesn't). See ADR-0002 in the deep-dive doc.

The citation validator performs five checks (existence, pointer, span support, claim strength, source authority). If any check fails, the claim is not published. Verified by `tests/test_citation.py`.

## Audit trail

Every state-changing tool call, AI proposal, and human decision produces an `AuditEntry` with `actor`, `actor_kind` (`human` or `agent`), `payload`, and `timestamp`. The trail is queryable via `get_audit_trail`, the HTTP API, and the review UI. A separate global log for read-only MCP calls and signed-PDF export remain future work.

## What is unfinished (honest list)

See the README's *What's unfinished* section. The headline gaps: LangGraph checkpoint resume not yet wired into the UI; run-to-run variance on the real model not measured (see EVALS.md); PDF ingestion tested only via Markdown; the external fetch server only tested manually.

## Deep dive

For the full architectural contract (rules, ADRs, schema, flow diagrams), see [docs/architecture-deep-dive.md](./docs/architecture-deep-dive.md).
