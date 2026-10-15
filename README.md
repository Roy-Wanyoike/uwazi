<div align="center">

# BidBox

### Open contracting intelligence for African procurement.

**An agentic AI on MCP that evaluates public tenders in 30 minutes — with a hard rule that the AI proposes and the procurement officer decides.**

Built for the [Agentic AI for Africa Innovation Challenge](https://agentic-africa-challenge.lovable.app/) — Governance track, Bid Box Challenge, *Digital economy / Open contracting* theme.

[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Tests](https://img.shields.io/badge/tests-33%20PASS-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![MCP](https://img.shields.io/badge/MCP-10%20tools-teal)]()
[![Orchestration](https://img.shields.io/badge/orchestration-LangGraph-orange)]()
[![Model](https://img.shields.io/badge/model-Qwen2.5--72B-purple)]()

</div>

---

## One command

```bash
git clone https://github.com/Roy-Wanyoike/bidbox.git
cd bidbox
./run-demo.sh
```

That's it. The script creates a venv, installs BidBox, seeds a real-shape Makueni County water tender + 3 bids, runs the LangGraph agent, demonstrates the human-in-the-loop boundary, and opens the procurement officer review UI at http://localhost:8000.

## What BidBox does

A procurement office receives a tender and N bids. Today the evaluation is a 26-day manual exercise — sorting bids, ticking off documents, checking each bidder, comparing prices, writing the report. BidBox turns it into a 30-minute officer-reviewed exercise, with a hard rule: **the agent prepares the file, it never awards the tender.**

The workflow:

1. **`ingest_tender`** — the agent reads the tender (PDF or Markdown), extracts the evaluation criteria with citations to specific paragraphs.
2. **`ingest_bid`** — the agent ingests each bid document against the tender.
3. **`evaluate_bids`** — a five-node LangGraph workflow runs per bid:
   - **ExtractorAgent** → criteria with citations
   - **BidAnalyzerAgent** → responses per criterion with citations
   - **ScorerAgent** → 0–10 score per (bid, criterion) pair with citations
   - **RiskAgent** → compliance risks per bid with citations
   - **OrchestratorAgent** → ranked report with per-bid recommendation
4. **`get_report`** — the procurement officer opens the report. Every score is one click from the source paragraph it was derived from.
5. **`record_officer_decision`** — the officer records `accept` / `reject` / `needs_review` per bid. **HUMAN-ONLY.** The agent never writes the decision — there is a SQL `CHECK + trigger` that refuses any agent-originated insert.
6. **`get_audit_trail`** — full audit trail of AI proposals + human decisions, exportable as a signed PDF for the procurement archive.

For the *Digital economy / Open contracting* theme, BidBox also exposes:

- **`open_notices`** — a citizen-facing tool that returns every active tender in plain English: eligibility checklist, mandatory documents, deadlines. No legalese, no AI inferences — just structured facts.
- **`explain_tender_in_plain_language`** — an AI-generated plain-language summary for a small supplier, citizen, or journalist. Every claim cites a paragraph. Stamped `ai_generated=True`.
- **`fetch_tender_notice`** — pulls a tender notice from a public procurement portal URL via the **official `mcp-server-fetch` MCP server** (a server BidBox did not write).

## The architectural rule (the most important sentence in this README)

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

Enforced at three layers — see [ARCHITECTURE.md](./ARCHITECTURE.md):

1. **SQL** — `CHECK (decided_by <> 'agent')` + `BEFORE INSERT` trigger on `decisions`. A judge can verify this in 60 seconds:
   ```bash
   sqlite3 bidbox.db "INSERT INTO decisions (id, tender_id, bid_id, decision, rationale, decided_by, decided_at) VALUES ('hack', 't', 'b', 'accept', 'agent hack', 'agent', datetime('now'));"
   # → Parse error: agent may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)
   ```
2. **MCP tool** — `record_officer_decision` refuses any request where `principal_kind='agent'`. Verified by `tests/test_human_in_the_loop.py`.
3. **Process** — the test suite runs on every commit.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| **MCP server** (built) | `mcp` Python SDK (FastMCP), 10 tools | The protocol surface for the entire workflow. |
| **MCP server** (borrowed) | Official `mcp-server-fetch` | Handles HTTP redirects, gzip, charset detection, HTML stripping, robots.txt, SSRF protection. ~500 LOC saved. |
| **Orchestration** | LangGraph (`StateGraph` + `MemorySaver`) | Open-source, Apache 2.0. The de-facto orchestrator for agent workflows with named-tool calls. |
| **LLM gateway** | `openai` SDK pointed at any OpenAI-compatible endpoint | Default: **Qwen2.5-72B-Instruct via ModelScope** (open-weights). Also supports OpenAI for side-by-side and local Llama via Ollama for fully on-prem. |
| **Document ingestion** | `pdfplumber` (PDF) + Markdown reader | Paragraph-level citation tracking — works for both PDFs (page-based) and Markdown (no pages). |
| **Storage** | SQLite (portable to Postgres) | Zero-config for the demo; portable for production. |
| **Review UI** | FastAPI + single HTML page | The procurement officer review screen. |
| **Tests** | `pytest` + `pytest-asyncio` | 33 tests, ~1.1s. |

## Project structure

```
bidbox/
├── README.md                  ← you are here
├── ARCHITECTURE.md            ← one-page architectural contract (judge-required)
├── EVALS.md                   ← 33 tests + 1 known unfixed failure (judge-required)
├── INVESTORS.md               ← market, business model, traction, roadmap
├── JUDGE_GUIDE.md             ← walks through every judging criterion
├── SUBMISSION_TEXT.md         ← 300-word submission text (judge-required)
├── SUBMISSION.md              ← build-window scope + 5 files to read first
├── DEMO_SCRIPT.md             ← 20-minute live review walkthrough
├── run-demo.sh                ← one-command demo
├── pyproject.toml
├── .env.example
├── docs/
│   └── architecture-deep-dive.md  ← the full ADR + schema contract
├── src/bidbox/
│   ├── config.py              ← env-driven settings
│   ├── models.py              ← Pydantic domain models
│   ├── db.py                  ← SQLite schema + audit trail + decision CHECK + trigger
│   ├── pdf.py                 ← PDF + Markdown ingestion, paragraph-level citations
│   ├── citation.py            ← 5-check citation validator (fails closed)
│   ├── gateway.py             ← provider-agnostic LLM gateway (STUB mode + real)
│   ├── prompts.py             ← every system + user prompt in one module
│   ├── agents.py              ← ExtractorAgent, BidAnalyzerAgent, ScorerAgent, RiskAgent
│   ├── orchestrator.py        ← LangGraph StateGraph (5 nodes, 1 conditional edge)
│   ├── external_mcp.py        ← integration with official mcp-server-fetch
│   ├── mcp_server.py          ← FastMCP server: 10 tools
│   ├── api.py                 ← FastAPI review UI
│   └── cli.py                 ← CLI driver
├── web/index.html             ← procurement officer review screen
├── samples/
│   ├── tender-makueni-water.md      ← synthetic tender (real-shape)
│   ├── tender-makueni-water.ocds.json ← same tender in OCDS (Open Contracting Data Standard)
│   ├── bid-aquaforce.md             ← clean bid
│   ├── bid-hydrotech.md             ← missing mandatory ISO 9001 (RiskAgent flag)
│   └── bid-sahara.md                ← anomalous-low financial (RiskAgent flag)
├── scripts/
│   ├── seed.py                ← seeds the sample tender + 3 bids
│   └── demo-video-script.md   ← 3-minute unedited video script
└── tests/
    ├── test_citation.py
    ├── test_pdf.py
    ├── test_human_in_the_loop.py
    └── test_mcp_tools.py
```

## Quick start (the long version)

If `./run-demo.sh` is too magical, here are the steps it runs:

```bash
git clone https://github.com/Roy-Wanyoike/bidbox.git
cd bidbox
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set OPENAI_API_KEY for real Qwen scores; leave blank for STUB

# 1. Seed the sample tender + 3 bids
python scripts/seed.py

# 2. Run the agentic evaluation
python -m bidbox.cli evaluate --tender-id makueni-water-2026

# 3. Demonstrate the human-in-the-loop boundary
python -m bidbox.cli demonstrate-human-in-the-loop --tender-id makueni-water-2026

# 4. Open the procurement officer review UI
python -m bidbox.cli serve    # → http://localhost:8000

# 5. (Optional) Drive BidBox from any MCP client
python -m bidbox.cli mcp      # stdio MCP server
```

## Documentation (read these in order if you are a judge)

1. [ARCHITECTURE.md](./ARCHITECTURE.md) — one page: agent shape, MCP servers built vs borrowed, the human-in-the-loop gate.
2. [EVALS.md](./EVALS.md) — 33 tests with pass/fail results + one known unfixed failure with next steps.
3. [JUDGE_GUIDE.md](./JUDGE_GUIDE.md) — walks through every judging criterion, points to exact files / commands.
4. [SUBMISSION_TEXT.md](./SUBMISSION_TEXT.md) — the 300-word submission text (theme, institution, workflow).
5. [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) — the 20-minute live review walkthrough.
6. [INVESTORS.md](./INVESTORS.md) — market size, business model, traction, roadmap.
7. [SUBMISSION.md](./SUBMISSION.md) — build-window scope + 5 files to read first.
8. [docs/architecture-deep-dive.md](./docs/architecture-deep-dive.md) — the full ADR + schema contract.

## What is unfinished (honest list)

The brief rewards honesty about what's unfinished. Here's the list:

- **Run-to-run variance on the real open-weights model is not measured.** STUB mode is deterministic; the real Qwen endpoint should be near-deterministic at `temperature=0.0` but I have not measured σ per criterion. See [EVALS.md](./EVALS.md) — this is the one failure I did not fix, with a concrete next-step plan.
- **LangGraph checkpoint resume is not yet wired into the UI.** The graph is compiled with `MemorySaver`, so an interrupted evaluation can in principle be resumed, but the review UI does not yet expose the resume button.
- **PDF ingestion is tested only via the Markdown path.** `pdf.py` supports PDFs via `pdfplumber`, but the test suite covers Markdown only. Committing a binary PDF would bloat the repo. To verify manually: `python -c "from bidbox.pdf import ingest_pdf; print(len(ingest_pdf('/path/to/real.pdf')))"`.
- **The external `mcp-server-fetch` is only tested manually.** The test suite verifies the fallback path (server not available → graceful degradation). The happy path (real URL fetch) requires a running subprocess.
- **I have not yet sat with a real Makueni procurement officer for a day.** The sample tender is shaped after reading publicly-available PPIP notices. The prompts + criteria weights reflect my reading, not a real officer's. With one more week of build time, that conversation is the first thing I would do.

## The architectural rule, restated one more time

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

If you remember one thing about BidBox, remember this. It is the difference between an agent that *assists* a procurement officer and an agent that *replaces* one. Procurement law across Africa puts the decision with a human committee. BidBox respects that — at the SQL layer.

## License

MIT. See [LICENSE](./LICENSE).

## Contact

Roy Wanyoike — Nairobi, Kenya. Repository at https://github.com/Roy-Wanyoike/bidbox.

<div align="center">

**AI recommends. The procurement officer decides.**

</div>
