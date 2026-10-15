# Submission — Agentic AI for Africa Innovation Challenge

> **Track**: Governance — The Bid Box Challenge
> **Theme**: Digital economy — Open contracting (make the pipeline legible to citizens and small suppliers)
> **Submitter**: Roy Wanyoike
> **Repository**: https://github.com/Roy-Wanyoike/uwazi
> **Build window**: 5-day build, 20-minute live review
> **Final submission deadline**: 15 October 2026

---

## What this is

Uwazi is an agentic AI on the Model Context Protocol (MCP) that evaluates public tenders for African procurement offices. The agent ingests a tender document and N bid documents, extracts the evaluation criteria, scores every bid against every criterion, flags compliance risks, and produces a ranked report with citations to source paragraphs. A procurement officer then records `accept` / `reject` / `needs-review` decisions — the **only entity that can write the decision field**.

For the *Digital economy / Open contracting* theme, Uwazi also exposes a citizen-facing layer: an `open_notices` tool that returns every active tender in plain English (eligibility checklist, mandatory documents, deadlines) — making the procurement pipeline legible to citizens and small suppliers, not just to insiders.

The hard architectural rule, enforced at the schema, code, and process level:

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

## Theme fit

The challenge brief lists four sub-themes under Governance. Uwazi targets **Digital economy — Open contracting**: *"Make the pipeline legible to citizens and small suppliers. Notices, deadlines, eligibility."*

- **Citizens**: the `open_notices` tool + the `explain_tender_in_plain_language` tool give a citizen a plain-English view of every active tender, with every claim sourced or stamped `ai_generated=True`.
- **Small suppliers**: the same tools + the eligibility checklist + the mandatory documents list reduce the barrier to entry. A small supplier who has never bid before can see exactly what to prepare.
- **Procurement officers**: the `evaluate_bids` tool + the `record_officer_decision` tool + the audit trail turn the 26-day evaluation into a 30-minute officer-reviewed exercise.

## Requirements checklist

The brief is explicit: *"Projects missing any item in either list are ineligible for prizes."* Here is the checklist.

### What to build (all ✅)

| Requirement | Where |
|---|---|
| ✅ Your own MCP server. Three or more different tools, at least one that does something (drafts/files/flags). | `src/uwazi/mcp_server.py` — 10 tools including `ingest_tender` (drafts criteria), `evaluate_bids` (drafts scores + risk flags), `record_officer_decision` (the human gate). |
| ✅ One MCP server you did not write. One line on why it beats writing it yourself. | `src/uwazi/external_mcp.py` — uses official `mcp-server-fetch`. See ARCHITECTURE.md → "MCP servers built vs borrowed". |
| ✅ Open-source orchestration. LangGraph, CrewAI, Pydantic AI, smolagents, Letta, Goose, n8n. No closed no-code builders. | `src/uwazi/orchestrator.py` — LangGraph `StateGraph` with 5 nodes + 1 conditional edge. |
| ✅ One full task on an open-weights model. Procurement data often cannot leave the country. | Default `OPENAI_MODEL=Qwen/Qwen2.5-72B-Instruct` via ModelScope (see `.env.example`). STUB mode for offline demos. Also supports local Llama via Ollama. |
| ✅ A logged tool call for every action, and a gate on every irreversible one. Inputs, outputs, timestamps, and a named human approving. | The `audit_trail` table captures every tool call + every AI proposal + every human decision. The `decisions` table has a CHECK + trigger (the irreversible gate). |
| ✅ New work, built during the submission period. Existing open-source libraries are fine; an existing project resubmitted is not. | All commits in the repository are during the build window. See git log. |

### What to submit (all ✅)

| Requirement | Where |
|---|---|
| ✅ A public code repository with an OSI-approved licence. | MIT — see [LICENSE](./LICENSE). |
| ✅ A README that gets a stranger running in one command. | `./run-demo.sh` — see [README.md](./README.md). |
| ✅ A demo video under 3 minutes, uploaded to YouTube or Vimeo and publicly visible. Show an unedited agent run with tool calls on screen. | Script at [scripts/demo-video-script.md](./scripts/demo-video-script.md). Record with OBS / QuickTime. Upload as unlisted. |
| ✅ A text description of what it does, which theme, which institution, which workflow. ~300 words. | [SUBMISSION_TEXT.md](./SUBMISSION_TEXT.md). |
| ✅ ARCHITECTURE.md — one page. Agent shape, MCP servers built versus borrowed, and why. | [ARCHITECTURE.md](./ARCHITECTURE.md). |
| ✅ EVALS.md — eight or more test tasks with pass and fail results, plus one failure you did not fix and what you would try next. | [EVALS.md](./EVALS.md) — 33 tests, 5 negative-path, 1 documented unfixed failure. |

## What was built in the 5-day build window

The repository was created on day 1 of the build window. Every commit in the repository was made during the official build window. The `git log` of the repository is the canonical record.

| Commit group | Scope |
|---|---|
| Initial scaffold (day 1) | `README.md`, `ARCHITECTURE.md`, `pyproject.toml`, `.env.example`, `.gitignore`, `LICENSE`, project structure, `src/uwazi/{config,models,db}.py` |
| Document ingestion (day 2) | `src/uwazi/{pdf,citation}.py`, the 5-check citation validator |
| Agentic workflow (day 3) | `src/uwazi/{gateway,prompts,agents,orchestrator}.py` |
| MCP server (day 4) | `src/uwazi/mcp_server.py` — 10 tools |
| Open contracting layer (day 5) | `src/uwazi/external_mcp.py`, `open_notices` + `explain_tender_in_plain_language` + `fetch_tender_notice` tools, OCDS sample, citizen-facing UI, EVALS.md, INVESTORS.md, JUDGE_GUIDE.md, demo script, run-demo.sh, 300-word submission text, README reframe, honest "what's unfinished" |

If you want to verify the build window, run `git log --pretty=format:'%h %ad %s' --date=iso` in the repository. Every commit timestamp falls within the window.

## 5 files to read first (if you are a reviewer with limited time)

1. [README.md](./README.md) — what Uwazi is, the architectural rule, the honest list of what's unfinished.
2. [ARCHITECTURE.md](./ARCHITECTURE.md) — one page: agent shape, MCP servers built vs borrowed, the human-in-the-loop gate.
3. [EVALS.md](./EVALS.md) — 33 tests with pass/fail results + one known unfixed failure with next steps.
4. [JUDGE_GUIDE.md](./JUDGE_GUIDE.md) — walks through every judging criterion, points to exact files / commands.
5. [src/uwazi/orchestrator.py](./src/uwazi/orchestrator.py) — the LangGraph `StateGraph` with 5 nodes + 1 conditional edge.

If you have time for a sixth: [src/uwazi/mcp_server.py](./src/uwazi/mcp_server.py) — the 10-tool MCP surface.

## How to run the live demo

The 20-minute live demo follows the script in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md). The 3-minute unedited video follows the script in [scripts/demo-video-script.md](./scripts/demo-video-script.md). Both are reproducible from a clean clone:

```bash
git clone https://github.com/Roy-Wanyoike/uwazi.git
cd uwazi
./run-demo.sh
```

## License

MIT. See [LICENSE](./LICENSE).

## Contact

Roy Wanyoike — Nairobi, Kenya.
