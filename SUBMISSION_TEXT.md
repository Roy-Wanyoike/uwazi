# Submission Text — around 300 words

**Project:** Uwazi — Evidence-first tender review
**Track:** Governance — The Bid Box Challenge
**Theme:** Digital economy — Open contracting
**Prototype institution:** Makueni County Government, Department of Water & Sanitation
**Workflow:** Preparing the committee's tender-evaluation file

Uwazi helps a county tender evaluation committee turn tender and bid documents into a defensible review pack. It is not an automated procurement officer. The agent extracts criteria, checks and scores each bid, flags missing documents and suspicious financials, then produces a ranked draft report with paragraph-level citations. It stops there. A named human records the decision.

That boundary is the heart of the project. The MCP tool and a database `CHECK` constraint and trigger block agent principals from writing decisions. AI proposals and human decisions are timestamped and attributed. If someone challenges a score, the reviewer can trace it to the tender paragraph and supplier response supporting it.

The workflow is a five-node LangGraph state machine rather than a single model call: extract criteria, analyze bids, score responses, flag risks, and compose the report. Uwazi exposes ten reusable MCP tools and borrows the official `mcp-server-fetch` server for robust public-notice retrieval. The configured open-weights path is Qwen2.5-72B-Instruct through ModelScope.

For the open-contracting theme, Uwazi turns stored notices into plain-language eligibility and document checklists for citizens and small suppliers. Public portals rarely publish confidential bids, so public data supplies notices while the evaluation demo uses synthetic documents and claims no county endorsement.

The repository is MIT-licensed, runs in one command, and includes 42 passing tests. The remaining submission-critical gaps are stated plainly: capture a real Qwen run, complete read-only tool-call logging, publish the unedited three-minute demo, and validate the workflow with a procurement professional.
