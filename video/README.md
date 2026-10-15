# Uwazi demo video

A 63-second end-to-end walkthrough of the deployed Uwazi platform running against a Neon Postgres database on Vercel. The video shows every step — ingestion state, evaluation workflow, ranked report with citations, audit trail, citizen-facing layer, and a live "Run agentic evaluation" click.

## File

- **`uwazi-demo.mp4`** — 1.1 MB, 62.6 seconds, H.264 1280×800, no audio.

## Scene-by-scene breakdown

| Time | Scene |
|---|---|
| 0:00 – 0:03 | **Landing page** — hero, badges, one-command clone. |
| 0:03 – 0:07 | **Ingestion proof** — `GET /api/v1/admin/seed-status` returns JSON showing 5 tenders × 15 bids seeded into Neon by the FastAPI lifespan handler on cold start. |
| 0:07 – 0:10 | **Tenders JSON** — `GET /api/v1/tenders` returns all 5 tenders with `bid_count=3` each. |
| 0:10 – 0:14 | **Tenders HTML page** — the rendered Next.js frontend shows 5 tender cards across 5 counties (Makueni Water, Nairobi Hospital Equipment, Mombasa Road Rehab, Kisumu School Furniture, Nakuru Solar Lighting). |
| 0:14 – 0:20 | **Makueni tender detail** — click into the first tender; the pre-evaluated ranked report renders with 3 bids (AquaForce, HydroTech, Sahara Civils), each with AI recommendation chip (`REJECT` in STUB mode), weighted score, risk flag count. |
| 0:20 – 0:25 | **Scroll — risk flags + scores** — risk flags expand with citations back to source paragraphs in the bid documents; "Show 6 scores with citations" expandable section. |
| 0:25 – 0:29 | **Scroll back to top** — the architectural rule banner is visible: *"The agent has proposed. Record accept / reject / needs_review decisions below. The agent cannot record decisions — only you can."* |
| 0:29 – 0:39 | **Live evaluation** — navigate to the Nairobi Hospital Equipment tender (no report yet) → click **Run agentic evaluation →** button → the LangGraph orchestrator runs the 5-node workflow (extract → analyze → score → flag → compose) → ranked report renders. |
| 0:39 – 0:42 | **Scroll the new report** — see the ranked bids + risk flags for the Nairobi tender. |
| 0:42 – 0:46 | **Audit trail** — `/audit/makueni-water-2026` page shows every AI proposal and human decision, timestamped and attributable. |
| 0:46 – 0:50 | **Open Notices** — the citizen-facing layer at `/notices` shows every active tender in plain English: eligibility checklists, mandatory documents. No legalese. |
| 0:50 – 0:53 | **Back to landing** — the final frame shows the stats grid (10 MCP tools, 5 LangGraph nodes, 42 tests passing, 26 → 30 days → minutes). |

## Live deployment

The video was recorded against the live deployment at
**https://uwazi-rose.vercel.app**. Visit it yourself to click through
the same flow, record decisions on each bid, and inspect the audit trail.

## Recording details

- Recorded with `agent-browser` (Playwright under the hood) at 30 fps
- Viewport: 1280 × 800
- Original format: WebM (2.1 MB)
- Delivered format: MP4 H.264 with `+faststart` for streaming (1.1 MB)
- The deployment uses STUB mode for LLM calls (no real Qwen API key
  configured), so every bid scores 0.0 — the workflow runs end-to-end
  but scores aren't differentiated. Set a real ModelScope inference
  token to see non-zero scores.
