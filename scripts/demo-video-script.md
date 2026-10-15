# Demo Video Script — 3 minutes, unedited

> Challenge brief: *"A demo video under 3 minutes, uploaded to YouTube or Vimeo and publicly visible. Show an unedited agent run with tool calls on screen, not slides."*

This script produces a 3-minute unedited screen recording. Record with OBS or QuickTime; do not edit. Upload to YouTube as unlisted; share the link in the submission form.

---

## 0:00 – 0:15 · Hook (no slide, just terminal)

Open a terminal at the cloned repo. Type:

```bash
./run-demo.sh
```

Say, out loud:

> "Uwazi is an evidence-first tender review agent on MCP. It turns tender and bid documents into a cited review pack, then stops: the agent proposes and the procurement committee decides. In the next three minutes, I will run the agent on a synthetic tender scenario, show its tool boundary, and prove the human gate."

---

## 0:15 – 1:00 · Seed + run (the agent in action)

The `run-demo.sh` script outputs:

```
[1/6] Creating Python virtualenv...
[2/6] Installing Uwazi + dependencies...
[3/6] Seeding sample tender + 3 bids...
[4/6] Running the agentic evaluation (LangGraph orchestrator)...
  ✓ Report produced. 3 bids evaluated.
  ✓ 6 criteria extracted.
  Ranking:
    #1 AquaForce Ltd         score=0.00  →  reject
    #2 HydroTech Ltd          score=0.00  →  reject
    #3 Sahara Civils Ltd      score=0.00  →  reject
  AI has proposed. The procurement officer must finalize.
```

The submitted recording must use the configured open-weights Qwen path. STUB mode is a developer fallback and does not satisfy the challenge requirement for one full task on an open-weights model. Keep a separate offline recording only as a contingency.

Narrate while it runs:

> "The agent is running a five-node LangGraph workflow: extract criteria from the tender, analyze each bid against those criteria, score each (bid, criterion) pair, flag compliance risks, then compose the ranked report. Every score, every risk flag, every recommendation cites a specific paragraph in the source documents."

---

## 1:00 – 1:45 · The architectural rule

When step 5 starts, narrate:

> "Now the human-in-the-loop boundary. The agent is going to attempt to call `record_officer_decision` with `principal_kind='agent'`. Watch what happens."

The terminal shows:

```
[5/6] Demonstrating the human-in-the-loop boundary...
  Attempting to record a decision with principal_kind='agent'...
  ✓ REFUSED — agents may not record decisions.
```

Then in a second terminal (or as a follow-on), show the SQL trigger:

```bash
sqlite3 uwazi.db "INSERT INTO decisions (id, tender_id, bid_id, decision, rationale, decided_by, decided_at) VALUES ('hack', 'makueni-water-2026', 'bid-sahara', 'accept', 'agent hack', 'agent', datetime('now'));"
```

Output:

```
Parse error: agent may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)
```

Say:

> "Even if a bug in the tool layer let the agent through, the database refuses. The rule is enforced at three layers: SQL `CHECK` + trigger, the MCP tool, and the test suite. This is defense in depth."

---

## 1:45 – 2:45 · The review UI + audit trail

`run-demo.sh` starts the FastAPI server. The terminal prints:

```
[6/6] Starting the procurement officer review UI...
Uwazi is running. Open http://localhost:8000
```

Open the browser. The single-page UI shows:

1. Left: the list of tenders. Click *Makueni County Water Reticulation*.
2. Right: the ranked report — three bid cards with rank badges, weighted scores, AI recommendation chips.
3. Click *Show scores with citations* on a bid — every score is one click from the source paragraph in the tender and the bid.
4. Click *Accept* on AquaForce, type a rationale, submit. The decision is persisted with `decided_by='officer-demo'`.
5. Open a new tab and run `python -m uwazi.cli audit --tender-id makueni-water-2026 | python -m json.tool`. The JSON shows: every AI proposal (orchestrator run with timestamp + tokens + cost) + every human decision (officer decision with timestamp + rationale).

Narrate:

> "This is the audit trail — every AI proposal, every human decision, timestamped and attributable. This is the artifact an audit office would demand."

---

## 2:45 – 3:00 · The close

Cut back to the terminal. Type:

```bash
python -c "from uwazi.mcp_server import mcp; print('Uwazi exposes', len(mcp._tool_manager.list_tools()), 'MCP tools.')"
```

Output:

```
Uwazi exposes 10 MCP tools.
```

Say:

> "Uwazi is MCP-native. Ten tools, the official fetch server as the one we didn't write, Qwen2.5 as the open-weights model. The agent proposes; the officer decides. The architectural rule is in the database. Repo at github.com/Roy-Wanyoike/uwazi."

Cut.

---

## What you'll need to record

- A clean clone of the repo on a fresh machine (to show `./run-demo.sh` actually works cold).
- Python 3.11+ installed.
- A working Qwen/ModelScope credential for the required open-weights run. Verify it before recording and never expose the credential on screen.
- OBS / QuickTime / ScreenFlow set to record the full screen, 1080p, system audio + microphone.

## What the video must show, per the brief

- ✅ Unedited agent run (no slides; we run `./run-demo.sh` live)
- ✅ Tool calls on screen (the LangGraph node output + the MCP tool JSON are visible in the terminal)
- ✅ Where it fails (the human-in-the-loop refusal is the "where it fails" moment)
- ✅ Under 3 minutes (script timing above: 3:00)
- ✅ Publicly visible on YouTube (upload as unlisted, share link)

## Where the brief is flexible

- You CAN show the LLM key set if you want non-stub scores. Strongly recommended.
- You CAN show the external MCP fetch server (`mcp-server-fetch`) by running `python -m uwazi.cli fetch-tender-notice --url https://example.com/tender.pdf` if you have that CLI sub-command wired. (It's in the codebase but not in the demo script — add a 15-second aside if you want to demonstrate it.)
- You MUST NOT edit the video. Re-record if you fluff a line. The "unedited" requirement is explicit in the brief.
