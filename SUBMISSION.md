# Submission — Agentic AI for Africa Innovation Challenge

> **Track**: Governance — The Bid Box Challenge
> **Submitter**: Roy Wanyoike
> **Repository**: https://github.com/Roy-Wanyoike/bidbox
> **Build window**: 5-day build, 20-minute live review

---

## What this is

BidBox is an agentic AI on the Model Context Protocol (MCP) that evaluates public tenders for African procurement offices. The agent ingests a tender document and N bid documents, extracts the evaluation criteria, scores every bid against every criterion, flags compliance risks, and produces a ranked report with citations to source paragraphs. A procurement officer then records `accept` / `reject` / `needs-review` decisions — **the only entity that can write the decision field**.

The hard architectural rule, enforced at the schema, code, and process level:

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

## What was built in the 5-day build window

The repository was created on day 1 of the build window. Every commit in the repository was made during the official build window. The `git log` of the repository is the canonical record.

| Commit group | Scope |
|---|---|
| Initial scaffold (day 1) | `README.md`, `ARCHITECTURE.md`, `pyproject.toml`, `.env.example`, `.gitignore`, `LICENSE`, project structure, `src/bidbox/{config,models,db}.py` |
| Document ingestion (day 2) | `src/bidbox/{pdf,citation}.py`, the citation validator |
| Agentic workflow (day 3) | `src/bidbox/{gateway,prompts,agents,orchestrator}.py` |
| MCP server (day 4) | `src/bidbox/mcp_server.py`, the 7-tool surface |
| Review UI + sample data + tests + demo script (day 5) | `src/bidbox/{api,cli}.py`, `web/index.html`, `samples/`, `scripts/seed.py`, `tests/`, `DEMO_SCRIPT.md` |

If you want to verify the build window, run `git log --pretty=format:'%h %ad %s' --date=iso` in the repository. Every commit timestamp falls within the window.

## What to read first (5 files)

If you are a reviewer with limited time, read these five files in this order:

1. [README.md](./README.md) — what BidBox is, what it does, the architectural rule.
2. [ARCHITECTURE.md](./ARCHITECTURE.md) — the four hard rules, the agentic workflow, the human-in-the-loop boundary.
3. [src/bidbox/mcp_server.py](./src/bidbox/mcp_server.py) — the 7 MCP tools. `record_officer_decision` is the human-in-the-loop gate.
4. [src/bidbox/orchestrator.py](./src/bidbox/orchestrator.py) — how the agent chains ExtractorAgent → BidAnalyzerAgent → ScorerAgent → RiskAgent.
5. [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) — the 20-minute live review walkthrough.

If you have time for a sixth file, read [src/bidbox/citation.py](./src/bidbox/citation.py) — the citation validator that fails closed when an AI claim cannot be grounded in source documents.

## How to run the live demo

The 20-minute live demo follows the script in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md). At a high level:

1. Seed the sample tender (*Makueni County Water Reticulation*) and the three sample bids (AquaForce, HydroTech, Sahara Civils).
2. Run the agentic evaluation: `python -m bidbox.cli evaluate --tender-id makueni-water-2026`.
3. Open the procurement officer review UI: `uvicorn bidbox.api:app --reload` → http://localhost:8000
4. Walk through the report. Every score, every risk flag, every recommendation is one click from the source paragraph.
5. Record `accept` / `reject` / `needs-review` decisions on each bid.
6. Show the audit trail — AI proposals + human decisions, exportable as a signed PDF for the procurement archive.
7. Demonstrate the human-in-the-loop boundary by attempting to call `record_officer_decision` with `principal.kind='agent'` — the tool refuses.

## How to drive BidBox from any MCP client

BidBox is MCP-native. The same tools the orchestrator calls are available to any MCP-compatible client:

```bash
# Start the MCP server (stdio transport)
python -m bidbox.mcp_server

# Or from a Python MCP client:
python -c "
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio, json

async def main():
    async with stdio_client(StdioServerParameters(command='python', args=['-m','bidbox.mcp_server'])) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps([t.name for t in tools.tools]))
            # call list_tenders
            result = await session.call_tool('list_tenders', {})
            print(result.content[0].text)

asyncio.run(main())
"
```

## The hard architectural rule, restated

This rule appears in three places — the README, the ARCHITECTURE, and here — because it is the single most important design decision in BidBox.

> **The agent may propose scores, risk flags, and recommendations. The agent may NEVER record a decision.**

It is enforced at three layers:

1. **Schema**: `CHECK (decided_by <> 'agent')` on the `decisions` table plus a `BEFORE INSERT` trigger that aborts any agent-originated write.
2. **Code**: the Python agent service has no direct DB credentials on the `decisions` table; it calls the MCP tool, which validates the principal.
3. **Process**: `tests/test_human_in_the_loop.py` asserts the agent cannot insert into `decisions`. This test runs on every commit.

## License

MIT. See [LICENSE](./LICENSE).

## Contact

Roy Wanyoike — Nairobi, Kenya.
