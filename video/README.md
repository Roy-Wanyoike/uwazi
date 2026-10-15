# Uwazi demo video

A 30-second walkthrough of the deployed Uwazi platform running end-to-end
against a Neon Postgres database on Vercel.

## File

- **`uwazi-demo.mp4`** — 590 KB, 30 seconds, H.264, no audio.

## What the video shows

| Time | Scene |
|---|---|
| 0:00 – 0:03 | Landing page — hero, badges, one-command clone |
| 0:03 – 0:06 | `/tenders` list — all 5 active tenders (Makueni Water, Nairobi Hospital Equipment, Mombasa Road Rehab, Kisumu School Furniture, Nakuru Solar Lighting) |
| 0:06 – 0:11 | Click into Makueni tender — ranked report renders with 3 bids (AquaForce, HydroTech, Sahara Civils), each with AI recommendation, weighted score, risk flag count |
| 0:11 – 0:16 | Scroll — risk flags expand with citations back to source paragraphs in the bid documents |
| 0:16 – 0:20 | Scroll back to top — architectural rule banner visible ("The agent has proposed. Record accept / reject / needs_review decisions below. The agent cannot record decisions — only you can.") |
| 0:20 – 0:24 | `/notices` — the citizen-facing Open Notices layer (eligibility checklists, mandatory documents in plain English) |
| 0:24 – 0:30 | Back to landing — feature cards + stats grid |

## Live deployment

The video was recorded against the live deployment at
**https://uwazi-rose.vercel.app**. Visit it yourself to click through
the same flow, record decisions on each bid, and inspect the audit trail.

## Recording details

- Recorded with `agent-browser` (Playwright under the hood) at 30 fps
- Viewport: 1280 × 800
- Original format: WebM (1.2 MB)
- Delivered format: MP4 H.264 (590 KB) — universally supported, smaller file size
- The deployment uses STUB mode for LLM calls (no real Qwen API key
  configured), so every bid scores 0.0 — the workflow runs end-to-end
  but scores aren't differentiated. Set a real ModelScope inference
  token to see non-zero scores.
