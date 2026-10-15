# Submission Text — 300 words

> Required by the challenge brief: *"A text description of what it does, which theme it fits, and which institution and workflow it serves. Around 300 words."*

---

**Project:** BidBox — Open Contracting Intelligence for African Procurement
**Track:** Governance — The Bid Box Challenge
**Theme:** Digital economy — Open contracting (make the pipeline legible to citizens and small suppliers)
**Institution:** Makueni County Government, Department of Water & Sanitation (Kenya)
**Workflow:** Tender evaluation — the 26-day committee exercise that sorts bids, ticks off mandatory documents, compares prices, and writes a defensible report.

**What it does**

BidBox is an agentic AI on the Model Context Protocol that evaluates public tenders in about thirty minutes, with a hard architectural rule: the agent proposes scores, risk flags, and recommendations; a procurement officer records the final decision. The rule is enforced at three layers — SQL `CHECK` + `BEFORE INSERT` trigger, the MCP tool refuses agent principals, and a test suite runs on every commit.

The agent is a five-node LangGraph state machine: extract criteria from the tender, analyze each bid against those criteria, score each (bid, criterion) pair, flag compliance risks (missing ISO 9001, abnormally low financials), compose a ranked report. Every score cites a specific paragraph in the source documents. Every AI output is stamped `ai_generated=True`. Every human decision is stamped `actor_kind=human`. The audit trail is queryable and exportable — the artifact an audit office would demand.

**Citizen-facing layer**

For the digital-economy / open-contracting theme, BidBox also exposes a `open_notices` MCP tool that returns every active tender in plain English: eligibility checklist, mandatory documents a small supplier must prepare, deadlines. No legalese, no AI inferences — just structured facts from the stored tender.

**Stack**

BidBox MCP server (built — 10 tools). Official `mcp-server-fetch` (borrowed — handles redirects, gzip, robots.txt, SSRF). LangGraph orchestration. Qwen2.5-72B-Instruct via ModelScope (open-weights). SQLite (portable to Postgres). MIT-licensed. 33 passing tests. Repository at https://github.com/Roy-Wanyoike/bidbox. One-command demo: `./run-demo.sh`.
