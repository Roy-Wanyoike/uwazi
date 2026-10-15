# BidBox

### An agentic AI on MCP that evaluates public tenders for African procurement offices.

**AI recommends. The procurement officer decides.**

Built for the [Agentic AI for Africa Innovation Challenge](https://agentic-africa-challenge.lovable.app/) — Bid Box track. Five days to build, twenty minutes live in your own code.

---

## What BidBox does

A procurement office receives a tender document and N bid documents. Today, evaluation is a days-long manual exercise: extract the criteria from the tender, score every bid against every criterion, flag compliance risks, rank the bids, write a defensible report. By the time the report is signed, the officer can barely remember why Bid 3 scored 7/10 on "technical capacity."

BidBox is an agentic AI on the Model Context Protocol (MCP) that turns this into a thirty-minute exercise — with a hard human-in-the-loop rule: the agent proposes, the procurement officer disposes.

The workflow:

1. `ingest_tender` — the agent reads the tender document (PDF or Markdown), extracts the evaluation criteria (eligibility, technical, financial, mandatory documents) with citations back to specific paragraphs.
2. `ingest_bid` — the agent ingests each bid document against the tender.
3. `evaluate_bids` — the orchestrator agent runs a four-stage workflow per bid:
   - **BidAnalyzerAgent** — extracts the bid's responses to each criterion, with citations to specific bid paragraphs.
   - **ScorerAgent** — scores each (bid, criterion) pair on a 0-10 rubric, with citations to both the tender passage that defines the criterion and the bid passage that responds to it.
   - **RiskAgent** — flags compliance risks per bid (missing mandatory documents, suspiciously low financials, late submissions, deviation from the rubric).
   - **OrchestratorAgent** — composes a ranked report with citations, scores, risk flags, and a recommendation per bid.
4. `get_report` — the procurement officer opens the report. Every score, every flag, every recommendation is one click away from the source paragraph it was derived from.
5. `record_officer_decision` — the procurement officer records `accept` / `reject` / `needs-review` decisions per bid, with a rationale. **Only humans can call this tool.** The agent never writes to the decision table — there is a SQL trigger that refuses inserts with `decided_by='agent'`.
6. `get_audit_trail` — full audit trail of AI proposals + human decisions, exportable as a signed PDF for the procurement archive.

## Why MCP

BidBox is MCP-native. Every capability — ingesting documents, extracting criteria, scoring bids, recording decisions — is exposed as an MCP tool. The orchestrator agent is an MCP client that calls the tools through the protocol. This means:

- Any MCP-compatible client (Claude Desktop, your IDE, a custom agent) can drive BidBox.
- The procurement office can swap the LLM (Qwen, GPT, Claude, local Llama) without touching the agent code.
- The human-in-the-loop boundary is enforced at the MCP tool layer: `record_officer_decision` is the only tool that writes to the decision table, and it requires a human principal.

## The architectural rule

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.** Every AI output is stamped `ai_generated=True`; the decision table has a SQL trigger that refuses any insert with `decided_by='agent'`.

This rule is enforced at three layers:
- **Schema**: the `decisions` table has a `CHECK (decided_by <> 'agent')` constraint.
- **Code**: the Python agent service has no write credentials on the `decisions` table; it calls the Go-free Python `record_officer_decision` tool via MCP, which validates the principal.
- **Process**: every commit that touches the orchestrator or the MCP server runs the test that the agent cannot record a decision.

## Tech stack

| Layer | Technology |
|---|---|
| MCP server | Python 3.12, official `mcp` SDK (FastMCP) |
| Agentic workflow | Python — OrchestratorAgent + 4 single-purpose agents |
| Document ingestion | `pdfplumber` (PDF) + Markdown reader — both with paragraph-level citation tracking |
| LLM gateway | `openai` SDK pointed at any OpenAI-compatible endpoint (Qwen via ModelScope, OpenAI, local Llama) |
| Storage | SQLite (zero-config) — portable to Postgres for production |
| Review UI | FastAPI + a single HTML page — procurement officer review screen |
| Tests | `pytest` + `pytest-asyncio` |

## Quick start

```bash
git clone https://github.com/Roy-Wanyoike/bidbox.git
cd bidbox
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env             # set OPENAI_API_KEY (or Qwen base URL)

# 1. Seed the sample tender + 3 bids
python scripts/seed.py

# 2. Run the agentic evaluation
python -m bidbox.cli evaluate --tender-id makueni-water-2026

# 3. Open the procurement officer review UI
uvicorn bidbox.api:app --reload    # → http://localhost:8000

# 4. (Optional) Drive BidBox from any MCP client
python -m bidbox.mcp_server        # stdio MCP server
```

## Sample data

The repo ships a synthetic tender — *Makueni County Water Reticulation Project* — and three synthetic bids (AquaForce, HydroTech, Sahara Civils) crafted to demonstrate the four hard cases:

| Bid | What it demonstrates |
|---|---|
| AquaForce Ltd | A clean, well-scoring bid. Shows the happy path. |
| HydroTech Ltd | A bid missing a mandatory document (ISO 9001 certificate). Shows the RiskAgent flagging compliance. |
| Sahara Civils | A bid with a suspiciously low financial quote (60% of the next-lowest). Shows the RiskAgent flagging anomaly. |

The sample is in Markdown (so you can read it on GitHub), but the ingestion pipeline handles PDFs identically — citations are by paragraph index, which works for both.

## Project structure

```
bidbox/
├── README.md
├── SUBMISSION.md           # 7-day build window scope + reviewer guide
├── ARCHITECTURE.md         # canonical architectural contract
├── DEMO_SCRIPT.md           # 20-minute live review walkthrough
├── pyproject.toml
├── .env.example
├── src/bidbox/
│   ├── config.py            # env-driven settings
│   ├── models.py            # Pydantic domain models
│   ├── db.py                # SQLite + audit trail + decision CHECK constraint
│   ├── pdf.py               # PDF + Markdown ingestion with citation tracking
│   ├── citation.py          # citation validator (5 checks, fails closed)
│   ├── gateway.py           # provider-agnostic LLM gateway
│   ├── prompts.py           # all system + user prompts in one module
│   ├── agents.py            # ExtractorAgent, BidAnalyzerAgent, ScorerAgent, RiskAgent
│   ├── orchestrator.py      # OrchestratorAgent — chains the 4 above via MCP tools
│   ├── mcp_server.py        # FastMCP server exposing 7 tools
│   ├── api.py               # FastAPI review UI
│   └── cli.py               # command-line driver
├── web/index.html           # procurement officer review screen
├── samples/                 # synthetic tender + 3 bids (Markdown)
├── scripts/seed.py          # seeds SQLite with the sample tender + bids
└── tests/                   # pytest suite
```

## Documentation

- [SUBMISSION.md](./SUBMISSION.md) — what was built in the 7-day window, what to read first
- [ARCHITECTURE.md](./ARCHITECTURE.md) — the architectural contract (rules + ADRs)
- [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) — the 20-minute live review script

## License

MIT. See [LICENSE](./LICENSE).
