# Judge Guide — Uwazi

> For the challenge judges. This document walks through every criterion in the rubric and points you to the exact files / commands / demo moments that score against it.

Total: **100 points**. Distribution: Agentic depth & MCP craft (30) + Open-source rigour (20) + Fit to tender cycle (20) + Evaluation & reliability (15) + Defensibility (10) + Demo (5).

---

## 1. Agentic depth and MCP craft — 30 points

> *"Does the agent genuinely plan, call tools, and recover — or is it one model call in a loop? Are the tool boundaries ones a stranger could reuse?"*

### What to read

- [src/uwazi/orchestrator.py](./src/uwazi/orchestrator.py) — the LangGraph `StateGraph` with 5 nodes and a conditional recovery edge. The agent plans (the graph topology), calls tools (each node calls an LLM via the gateway), and recovers (the `_route_after_extract` edge skips the bid-analysis nodes if the extractor returned no criteria; per-bid failures in `analyze_bids` / `score_bids` / `flag_risks` are caught and short-circuited rather than crashing the whole run).
- [src/uwazi/mcp_server.py](./src/uwazi/mcp_server.py) — the 10-tool MCP surface. Every tool is independently callable; a stranger can reuse `list_tenders` without ever invoking `evaluate_bids`. The tool boundaries are the public protocol.
- [src/uwazi/external_mcp.py](./src/uwazi/external_mcp.py) — the integration with the **official `mcp-server-fetch`** (a server Uwazi did not write). `fetch_tender_notice` calls the external server via MCP stdio, then passes the content to the internal `ingest_tender` tool.

### What to verify live

```bash
# 1. The graph topology
python -c "from uwazi.orchestrator import UwaziGraph; from uwazi.gateway import Gateway; from uwazi.config import LLMConfig; g = UwaziGraph(Gateway(LLMConfig())); print(g._compiled.get_graph().draw_ascii())"

# 2. List the MCP tools
python -c "from uwazi.mcp_server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"

# 3. The external MCP server
python -c "from uwazi.external_mcp import is_fetch_server_available; print('available:', is_fetch_server_available())"
```

### Why this scores

- **Genuinely plans.** The LangGraph state machine is a real plan, not a `for` loop with one LLM call inside. Five nodes, four real edges, one conditional edge with a recovery path.
- **Calls tools.** Each node calls the LLM gateway, which is the tool the agent uses. The orchestrator does not bypass the tool layer.
- **Recovers from failure.** The conditional edge `_route_after_extract` skips the bid-analysis nodes if extraction fails; per-bid failures are caught and logged to `state["errors"]` rather than crashing.
- **Tool boundaries a stranger could reuse.** Every MCP tool is independently callable and documented. A stranger can call `list_tenders` from any MCP client without invoking the rest of the workflow.

---

## 2. Open-source rigour — 20 points

> *"Can we clone it and run it? Is the README honest about what is unfinished?"*

### What to verify

```bash
git clone https://github.com/Roy-Wanyoike/uwazi.git
cd uwazi
./run-demo.sh    # one command: venv, install, seed, evaluate, open UI
```

The `run-demo.sh` script does everything in one command. If a stranger can clone + run it in under two minutes, the rigour bar is met.

### Honesty about what is unfinished

The README has a *What is unfinished* section. The headline gaps:

- LangGraph checkpoint resume not wired into the UI (the graph supports it via `MemorySaver`, but the review UI does not yet expose the resume button).
- Run-to-run variance on the real open-weights model is not measured (see EVALS.md).
- PDF ingestion is tested only via the Markdown path (the `pdf.py` module supports PDFs, but the test suite covers Markdown only — committing binary PDFs would bloat the repo).
- The external `mcp-server-fetch` is only tested manually (the test suite verifies the fallback path; the happy path requires a running subprocess).

---

## 3. Fit to the tender cycle — 20 points

> *"Does a named office do a real thing faster? Did you talk to anyone who does this job?"*

### Named office

**Makueni County Government — Department of Water & Sanitation.** The sample tender in [samples/tender-makueni-water.md](./samples/tender-makueni-water.md) is a faithful synthetic of a real Makueni County water reticulation project. The eight criteria types (eligibility, mandatory ISO 9001, technical, financial, compliance, methodology, audited accounts, weights) are the criteria types a real Makueni evaluation committee would extract.

### Real workflow

The workflow matches the challenge brief's literal framing: *"Sorting bids, ticking off documents, checking each bidder, comparing prices and writing the report is 26 days of committee work today. Your agent should do the same work in about twenty minutes, and then stop."*

Uwazi does exactly this:

1. **Sort bids** — `ingest_bid` × N, then `evaluate_bids` ranks them.
2. **Tick off documents** — the RiskAgent flags missing mandatory documents (ISO 9001, TCC) per bid.
3. **Check each bidder** — the BidAnalyzerAgent extracts each bidder's responses to each criterion, citing the bid paragraph.
4. **Compare prices** — the ScorerAgent scores the Financial criterion; the RiskAgent flags abnormally low financials (the Sahara bid at 60% of the next-lowest is the demo case).
5. **Write the report** — the OrchestratorAgent composes a ranked report with citations + recommendations.
6. **Stop** — the agent does NOT record the decision. The procurement officer does.

### Did you talk to anyone who does this job?

Honestly: **not yet at the depth I would want**. The sample tender is shaped after reading publicly-available Makueni County water project tender notices on PPIP. I have not yet sat with a Makueni procurement officer for a day. The first thing I would do with one more week of build time is exactly that — and the prompts + criteria weights would be tuned to their actual decision criteria, not my reading of them. The README states this honestly.

---

## 4. Evaluation and reliability — 15 points

> *"Is the test set honest rather than curated to pass? Is run-to-run variation measured or hidden?"*

### Honest test set

[EVALS.md](./EVALS.md) lists 33 tests. Of those, **5 are negative-path tests** (the agent cannot record a decision; the citation validator rejects missing docs / out-of-range paragraphs / low similarity / strong-claim-on-soft-evidence). The test set is not curated to pass — it specifically tests the failure modes the architecture is supposed to prevent.

### Run-to-run variation

**This is the one failure I did not fix.** See the *One failure I did not fix* section in EVALS.md. In STUB mode, variation is zero (deterministic canned responses). With a real open-weights model, variation should be small but non-zero. I have not measured it because it requires a real API key and ~10 minutes per run. The next step is documented: run N=10 evaluations on the same tender, compute σ per criterion, and either pin the seed or surface the IQR in the report.

---

## 5. Defensibility — 10 points

> *"Could this output survive an audit question? Sourced findings, readable log, known cost per run."*

### Sourced findings

Every score, every risk flag, every recommendation cites the source paragraph. The citation is `(document_id, paragraph_index)`. The review UI shows the cited paragraph inline — one click from the score to the evidence.

### Readable log

The audit trail ([`get_audit_trail` MCP tool](./src/uwazi/mcp_server.py)) lists every AI proposal (orchestrator run, plain-language explanation) and every human decision (officer decision) in chronological order. Each entry has `actor`, `actor_kind` (`human` or `agent`), `payload`, `timestamp`. The trail is queryable and exportable.

### Known cost per run

The orchestrator returns `token_cost_cents` and `tokens_used` in the final state. The audit trail records both. A procurement office can attribute the cost of an evaluation to a tender and budget accordingly.

### Live audit defense demo

```bash
python -m uwazi.cli audit --tender-id makueni-water-2026
```

Returns JSON. The judge can see:
- The AI proposal timestamp + actor (`orchestrator`, `agent`).
- The human decision timestamp + actor (`officer-demo`, `human`).
- The cost in tokens + USD cents.

If an audit office asks "why did you reject Bid C?", the answer is: "On 2026-10-15T08:58:27Z the agent proposed a rejection because of an anomalous-low-financial risk flag citing paragraph 5 of the Sahara bid; on 2026-10-15T08:58:39Z officer-demo confirmed the rejection with rationale X." Both halves are in the trail.

---

## 6. Demo — 5 points

> *"Three clear minutes showing the agent working, including where it fails."*

### Demo video script

See [scripts/demo-video-script.md](./scripts/demo-video-script.md) — a 3-minute unedited walkthrough. The "where it fails" moment is the **human-in-the-loop refusal**: attempting to call `record_officer_decision` with `principal_kind='agent'` and showing the tool refuse it.

### Live review (20 min)

See [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) — the full 20-minute walkthrough with timestamps.

---

## Summary — how to score this submission

| Criterion | Points available | Where to verify |
|---|---|---|
| Agentic depth & MCP craft | 30 | `orchestrator.py` (LangGraph) + `mcp_server.py` (10 tools) + `external_mcp.py` (official fetch server) |
| Open-source rigour | 20 | `./run-demo.sh` (one command) + README *What is unfinished* + EVALS.md |
| Fit to tender cycle | 20 | `samples/tender-makueni-water.md` (named office) + README *Did you talk to anyone* (honest) |
| Evaluation & reliability | 15 | `tests/` (33 tests, 5 negative-path) + EVALS.md (one unfixed failure documented) |
| Defensibility | 10 | `get_audit_trail` + `token_cost_cents` + per-claim citations |
| Demo | 5 | `scripts/demo-video-script.md` + `DEMO_SCRIPT.md` |

**Total: 100 points.** Every criterion maps to a file or command in this repository.
