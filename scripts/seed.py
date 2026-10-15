"""Seed all sample tenders + their bids into Uwazi.

Usage:
    python scripts/seed.py

This script ingests 5 synthetic tenders and 15 bids (3 per tender) into
the Uwazi database, using the same MCP tools the agent uses. Each
tender demonstrates a different scenario:

  * Makueni Water Reticulation — clean / missing ISO 9001 / anomalous-low financial
  * Nairobi Hospital Equipment — clean / missing ISO 13485 / anomalous-low financial
  * Mombasa Road Rehabilitation — clean / NCA Category B (not A) / anomalous-low financial
  * Kisumu School Furniture — clean / missing KEBS certification / anomalous-low financial
  * Nakuru Solar Street Lighting — clean / EPRA Category B (not A) / anomalous-low financial

After seeding, run:
    python -m uwazi.cli evaluate --tender-id <tender-id>
    python -m uwazi.cli serve    # → http://localhost:8000
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src/ is on the path when running scripts/ directly
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from uwazi.mcp_server import ingest_bid, ingest_tender  # noqa: E402


SAMPLES = ROOT / "samples"

# (tender_id, tender_path, title, issuer, [(bid_id, bid_path, bidder_name), ...])
TENDERS = [
    (
        "makueni-water-2026",
        SAMPLES / "tender-makueni-water.md",
        "Makueni County Water Reticulation Project",
        "Government of Makueni County — Department of Water & Sanitation",
        [
            ("bid-aquaforce", SAMPLES / "bid-aquaforce.md", "AquaForce Ltd"),
            ("bid-hydrotech", SAMPLES / "bid-hydrotech.md", "HydroTech Ltd"),
            ("bid-sahara", SAMPLES / "bid-sahara.md", "Sahara Civils Ltd"),
        ],
    ),
    (
        "nairobi-health-equipment-2026",
        SAMPLES / "tender-nairobi-health-equipment.md",
        "Nairobi County Hospital Equipment Supply",
        "Nairobi City County — Department of Health Services",
        [
            ("bid-nairobi-medequip", SAMPLES / "bid-nairobi-medequip.md", "MedEquip Africa Ltd"),
            ("bid-nairobi-healthtech", SAMPLES / "bid-nairobi-healthtech.md", "HealthTech Distributors"),
            ("bid-nairobi-sahara", SAMPLES / "bid-nairobi-sahara.md", "Sahara Medical Imports"),
        ],
    ),
    (
        "mombasa-road-rehab-2026",
        SAMPLES / "tender-mombasa-road-rehab.md",
        "Mombasa County Road Rehabilitation Project",
        "Mombasa County Government — Department of Roads & Public Works",
        [
            ("bid-mombasa-coastbuild", SAMPLES / "bid-mombasa-coastbuild.md", "CoastBuild Contractors Ltd"),
            ("bid-mombasa-highway", SAMPLES / "bid-mombasa-highway.md", "Highway Civils Ltd"),
            ("bid-mombasa-fasttrack", SAMPLES / "bid-mombasa-fasttrack.md", "FastTrack Civils"),
        ],
    ),
    (
        "kisumu-school-furniture-2026",
        SAMPLES / "tender-kisumu-school-furniture.md",
        "Kisumu County School Furniture Supply",
        "Kisumu County Government — Department of Education",
        [
            ("bid-kisumu-lakecraft", SAMPLES / "bid-kisumu-lakecraft.md", "LakeCraft Furniture Ltd"),
            ("bid-kisumu-comfort", SAMPLES / "bid-kisumu-comfort.md", "Comfort Seats Ltd"),
            ("bid-kisumu-lakeregion", SAMPLES / "bid-kisumu-lakeregion.md", "Lake Region Fabrications"),
        ],
    ),
    (
        "nakuru-solar-lighting-2026",
        SAMPLES / "tender-nakuru-solar-lighting.md",
        "Nakuru County Solar Street Lighting Project",
        "Nakuru County Government — Department of Energy",
        [
            ("bid-nakuru-solarbright", SAMPLES / "bid-nakuru-solarbright.md", "SolarBright Africa Ltd"),
            ("bid-nakuru-brightvolt", SAMPLES / "bid-nakuru-brightvolt.md", "BrightVolt Solutions"),
            ("bid-nakuru-sahara", SAMPLES / "bid-nakuru-sahara.md", "Sahara Solar Distributors"),
        ],
    ),
]


async def seed() -> int:
    print("=" * 60)
    print("Uwazi — seeding 5 sample tenders + 15 bids")
    print("=" * 60)

    for i, (tender_id, tender_path, title, issuer, bids) in enumerate(TENDERS, start=1):
        # Tender
        print(f"\n[{i}/5] Ingesting tender: {title}")
        result = ingest_tender(
            path=str(tender_path),
            tender_id=tender_id,
            title=title,
            issuer=issuer,
            country_code="KE",
        )
        import json
        tender_d = json.loads(result)
        print(f"  tender_id={tender_d.get('tender_id')} paragraphs={tender_d.get('paragraphs')}")

        # Bids
        for j, (bid_id, bid_path, bidder_name) in enumerate(bids, start=1):
            print(f"  [{i}.{j}/5.{len(bids)}] Bid: {bidder_name}")
            result = ingest_bid(
                tender_id=tender_id,
                path=str(bid_path),
                bidder_name=bidder_name,
                bid_id=bid_id,
            )

    print("\n" + "=" * 60)
    print("Seeded 5 tenders × 3 bids = 15 documents.")
    print("Next steps:")
    print("  1. python -m uwazi.cli evaluate --tender-id <tender-id>")
    print("  2. python -m uwazi.cli serve    # → http://localhost:8000")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(seed()))
