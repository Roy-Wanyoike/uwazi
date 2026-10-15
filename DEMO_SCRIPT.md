# Demo Script — 20-minute live review

> **Track**: Governance — The Bid Box Challenge
> **Format**: 20 minutes live in your own code
> **Audience**: The challenge judges + Qhala + Nairobi AI Community + IBM / Microsoft / AAIF / MCP

This script is a second-by-second walkthrough. It is reproducible from the repository as-is, with no pre-baked demo state. Run it from a clean clone of the repository.

---

## 0:00 – 2:00 · The pitch (one slide, one sentence)

Open the [README](./README.md) and the [SUBMISSION.md](./SUBMISSION.md). Show:

- **The problem.** Public procurement in African institutions takes days of manual evaluation. A single tender can attract dozens of bids; a procurement officer reads each bid against every criterion, scores it, flags compliance risks, and writes a defensible report — by hand, in a Word document, with no audit trail.
- **The architectural rule.** *"The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision."* Say this out loud. Show the SUBMISSION.md section that restates it. This is the slide that earns the track's "human-in-the-loop" requirement.

The one sentence: "BidBox is an agentic AI on MCP that turns tender evaluation from a days-long manual exercise into a 30-minute officer-reviewed exercise — with a hard rule that the AI proposes and the officer decides."

---

## 2:00 – 4:00 · The architecture

Open [ARCHITECTURE.md](./ARCHITECTURE.md). Walk through the four rules and the agentic workflow diagram in 60 seconds:

```
Tender PDF/MD → ExtractorAgent → criteria[]
Bid PDF/MD × N → BidAnalyzerAgent → responses[]
                → ScorerAgent → scores[]
                → RiskAgent → risk_flags[]
OrchestratorAgent → ranked report
Procurement officer → record_officer_decision
```

Stop on the SQL schema block (the `CHECK (decided_by <> 'agent')` constraint + the `BEFORE INSERT` trigger). This is where the audience leans forward — the human-in-the-loop rule is not a UX choice, it is enforced at three layers.

Mention: every capability is an MCP tool, so any MCP-compatible client (Claude Desktop, the MCP CLI, a custom agent) can drive the workflow. The LLM is provider-agnostic — Qwen via ModelScope, OpenAI, or a local Llama.

---

## 4:00 – 6:00 · Seed the sample

In a terminal:

```bash
git clone https://github.com/Roy-Wanyoike/bidbox.git
cd bidbox
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # OPENAI_API_KEY blank → STUB mode (deterministic, no network)

python scripts/seed.py
```

You should see:

```
[1/4] Ingesting tender: tender-makueni-water.md
[2/4] Ingesting bid: AquaForce Ltd (bid-aquaforce.md)
[3/4] Ingesting bid: HydroTech Ltd (bid-hydrotech.md)
[4/4] Ingesting bid: Sahara Civils Ltd (bid-sahara.md)
Seeded. Tender ID: makueni-water-2026
```

Open the three sample files in [samples/](./samples/) on screen:

- **tender-makueni-water.md** — 8 numbered sections, each defining a criterion (eligibility, mandatory ISO 9001, technical, financial, etc.).
- **bid-aquaforce.md** — a clean bid. Every criterion met. Annexes referenced.
- **bid-hydrotech.md** — clean bid, *but* the ISO 9001 certificate has lapsed and the bidder asks for the evaluation committee's "consideration." This is the missing-mandatory-document case.
- **bid-sahara.md** — a financial quote of KES 9.4M against the KES 22M estimated value (60% below the next-lowest). This is the anomalous-low-bid case.

The samples are Markdown — so the audience can read them on GitHub. The pipeline handles PDFs identically (citations are by paragraph index, see ADR-0002).

---

## 6:00 – 9:00 · Run the agentic evaluation

```bash
python -m bidbox.cli evaluate --tender-id makueni-water-2026
```

This calls the `evaluate_bids` MCP tool, which:

1. Loads the tender paragraphs + each bid's paragraphs.
2. Runs `ExtractorAgent` against the tender — extracts 8 criteria with citations to specific tender paragraphs.
3. For each bid: `BidAnalyzerAgent` extracts responses per criterion with citations to specific bid paragraphs.
4. For each (bid, criterion): `ScorerAgent` scores on a 0–10 scale, citing both the tender paragraph that defines the criterion and the bid paragraph that responds to it.
5. For each bid: `RiskAgent` flags compliance risks (missing mandatory document, anomalous-low financial, etc.) with citations.
6. The orchestrator composes a ranked report. The bids are ranked: award > shortlist > reject, then by weighted score.

The CLI prints the ranked summary:

```json
{
  "report_id": "...",
  "tender_id": "makueni-water-2026",
  "bids_evaluated": 3,
  "criteria_extracted": 8,
  "ranking": [
    {"rank": 1, "bid_id": "bid-aquaforce", "weighted_score": 7.8, "recommendation": "award", "risk_flags": 0},
    {"rank": 2, "bid_id": "bid-hydrotech", "weighted_score": 6.1, "recommendation": "shortlist", "risk_flags": 1},
    {"rank": 3, "bid_id": "bid-sahara", "weighted_score": 3.4, "recommendation": "reject", "risk_flags": 1}
  ],
  "ai_generated": true,
  "note": "AI has proposed. The procurement officer must call record_officer_decision to finalize."
}
```

Talk to the audience while it runs: "Notice the recommendation is a proposal, not a decision. The agent stamps every output `ai_generated=True`. The decision field is in a different table — and the SQL trigger refuses any agent-originated insert."

---

## 9:00 – 13:00 · The review UI (the human-in-the-loop)

```bash
python -m bidbox.cli serve   # http://localhost:8000
```

Open the browser. The single-page UI shows:

1. **Left:** the list of tenders. Click *Makueni County Water Reticulation Project*.
2. **Right:** the ranked report.
   - Each bid is a card. Rank badge, weighted score, AI recommendation chip.
   - **AquaForce** — `AWARD` recommendation, 0 risk flags. Show the score breakdown (click *Show scores with citations*): each score cites the tender paragraph that defines the criterion + the bid paragraph that responds.
   - **HydroTech** — `SHORTLIST` recommendation, 1 risk flag: `missing_mandatory_document — ISO 9001 certificate lapsed; re-certification scheduled for 15 December 2026`. Click the citation drill-down to see the exact paragraph in the bid that triggered the flag.
   - **Sahara** — `REJECT` recommendation, 1 critical risk flag: `anomalous_low_financial — the financial quote is 60% below the next-lowest bid`. Cite regulation 47 (abnormally low bids).

3. **The decision box.** For each bid, three buttons: `Accept`, `Needs review`, `Reject`. Each requires a rationale (min 10 chars). Click `Accept` on AquaForce, type "Highest scoring bid, meets all mandatory criteria," submit. The decision is persisted with `decided_by='officer-demo'` and added to the audit trail.

4. The architectural rule banner at the top stays visible: *"The agent may propose... The agent may NEVER record a decision. Enforced at the SQL layer (CHECK + trigger)."*

---

## 13:00 – 16:00 · Demonstrate the human-in-the-loop boundary

Open a second terminal. Run the demo command:

```bash
python -m bidbox.cli demonstrate-human-in-the-loop --tender-id makueni-water-2026
```

This attempts to call `record_officer_decision` with `principal_kind='agent'`. The tool refuses:

```json
{
  "error": "agents may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)",
  "tender_id": "makueni-water-2026",
  "bid_id": "any-bid"
}
```

Now show what happens if you bypass the tool layer and try to write directly to the database:

```bash
sqlite3 bidbox.db "INSERT INTO decisions (id, tender_id, bid_id, decision, rationale, decided_by, decided_at) VALUES ('hack', 'makueni-water-2026', 'bid-sahara', 'accept', 'agent hack', 'agent', datetime('now'));"
```

Output:

```
Parse error: agent may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)
```

That is the SQL trigger. Even if a bug in the tool layer let the agent through, the database refuses. This is defense in depth.

---

## 16:00 – 18:00 · The audit trail

```bash
python -m bidbox.cli audit --tender-id makueni-water-2026
```

Returns JSON listing every AI proposal (the orchestrator's report, every score, every risk flag) and every human decision (officer-1's `accept` on AquaForce), in chronological order. Mention: this is exportable as a signed PDF for the procurement archive — that's the compliance artifact a real audit office would demand.

Show the audit entry for the orchestrator run:

```json
{
  "id": "audit-...",
  "timestamp": "2026-10-15T...",
  "actor": "orchestrator",
  "actor_kind": "agent",
  "entry_kind": "ai_proposal",
  "payload": {
    "report_id": "...",
    "bids": 3,
    "criteria": 8,
    "scores": 24,
    "risk_flags": 2,
    "token_cost_cents": "0.0"
  }
}
```

Every AI proposal is timestamped, attributed, and stamped `actor_kind=agent`. Every human decision is timestamped, attributed, and stamped `actor_kind=human`. The trail is the compliance artifact.

---

## 18:00 – 20:00 · The "why MCP" pitch + close

Three things the judges should remember:

1. **MCP-native.** Every capability is an MCP tool. The orchestrator is an MCP client. The procurement office can mount BidBox's MCP server alongside their existing tools (file system, calendar, email) and let a higher-level agent compose across them. Show the [mcp_server.py](./src/bidbox/mcp_server.py) file — the tool list is the protocol surface.

2. **Provider-agnostic.** The same code runs on Qwen via ModelScope, OpenAI, or a local Llama. Show the [gateway.py](./src/bidbox/gateway.py) — one `complete()` method, no vendor lock-in. The demo ran in STUB mode (no API key needed) but the production gateway calls any OpenAI-compatible endpoint.

3. **The architectural rule.** *"The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision."* Say this one more time. It is the slide that earns the track's "AI recommends, a human-in-the-loop decides" requirement. Show the [SUBMISSION.md](./SUBMISSION.md) section that restates it. Show the test that runs on every commit: [tests/test_human_in_the_loop.py](./tests/test_human_in_the_loop.py).

Close with the one-liner:

> "BidBox turns a days-long manual tender evaluation into a 30-minute officer-reviewed exercise — with a hard architectural rule that the AI proposes and the procurement officer decides, enforced at three layers including the database itself."

---

## Appendix — fallbacks if something breaks

| Issue | Fallback |
|---|---|
| Internet is flaky | STUB mode (no API key) — the demo runs deterministically offline. |
| A tool call fails | Show the relevant test file — the test suite demonstrates the same behaviour. |
| Browser doesn't open | Run `python -m bidbox.cli report --tender-id makueni-water-2026` and show the JSON in the terminal. |
| SQLite is not installed | The Python `sqlite3` module is in the stdlib — it always works. |
| You're over time | Skip the audit trail section (16:00–18:00) and the human-in-the-loop demo (13:00–16:00). Keep the architecture walk (2:00–4:00) — that is the most important section. |

---

## Appendix — the five files the reviewer should read

If the reviewer has 10 minutes, point them at:

1. [README.md](./README.md) — what BidBox is and the architectural rule.
2. [ARCHITECTURE.md](./ARCHITECTURE.md) — the four hard rules + the human-in-the-loop boundary.
3. [src/bidbox/mcp_server.py](./src/bidbox/mcp_server.py) — the 7 MCP tools.
4. [src/bidbox/orchestrator.py](./src/bidbox/orchestrator.py) — how the agent chains the four sub-agents.
5. [tests/test_human_in_the_loop.py](./tests/test_human_in_the_loop.py) — the test that proves the agent cannot record a decision.

That's the whole submission. Everything else is implementation detail.
