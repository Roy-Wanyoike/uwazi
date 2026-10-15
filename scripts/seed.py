"""Seed the sample tender + 3 bids into BidBox.

Usage:
    python scripts/seed.py

This script ingests the synthetic Makueni Water Reticulation tender and
the three synthetic bids (AquaForce, HydroTech, Sahara Civils) into
the BidBox database, using the same MCP tools the agent uses.

After seeding, run:
    python -m bidbox.cli evaluate --tender-id makueni-water-2026
    python -m bidbox.cli serve    # http://localhost:8000

The sample is intentionally designed to exercise the four hard cases:

  * AquaForce  — clean, well-scoring bid. Happy path.
  * HydroTech  — missing ISO 9001 certificate (mandatory). RiskAgent flag.
  * Sahara     — financial quote 60% below the next-lowest bid. RiskAgent flag.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src/ is on the path when running scripts/ directly
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bidbox.mcp_server import ingest_bid, ingest_tender  # noqa: E402


SAMPLES = ROOT / "samples"
TENDER_PATH = SAMPLES / "tender-makueni-water.md"
TENDER_ID = "makueni-water-2026"

BIDS = [
    ("bid-aquaforce", SAMPLES / "bid-aquaforce.md", "AquaForce Ltd"),
    ("bid-hydrotech", SAMPLES / "bid-hydrotech.md", "HydroTech Ltd"),
    ("bid-sahara", SAMPLES / "bid-sahara.md", "Sahara Civils Ltd"),
]


async def seed() -> int:
    print("=" * 60)
    print("BidBox — seeding sample data")
    print("=" * 60)

    # --- Tender ---
    print(f"\n[1/4] Ingesting tender: {TENDER_PATH.name}")
    result = ingest_tender(
        path=str(TENDER_PATH),
        tender_id=TENDER_ID,
        title="Makueni County Water Reticulation Project",
        issuer="Government of Makueni County — Department of Water & Sanitation",
        country_code="KE",
    )
    print(result)

    # --- Bids ---
    for i, (bid_id, path, bidder) in enumerate(BIDS, start=2):
        print(f"\n[{i}/4] Ingesting bid: {bidder} ({path.name})")
        result = ingest_bid(
            tender_id=TENDER_ID,
            path=str(path),
            bidder_name=bidder,
            bid_id=bid_id,
        )
        print(result)

    print("\n" + "=" * 60)
    print(f"Seeded. Tender ID: {TENDER_ID}")
    print("Next steps:")
    print(f"  1. python -m bidbox.cli evaluate --tender-id {TENDER_ID}")
    print(f"  2. python -m bidbox.cli serve    # → http://localhost:8000")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(seed()))
