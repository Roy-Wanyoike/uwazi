"""CLI driver — `python -m bidbox.cli <command>`.

Used for the demo: seed → evaluate → open the review UI.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from .config import get_settings


@click.group()
def cli() -> None:
    """BidBox — agentic AI for tender evaluation."""
    pass


@cli.command()
@click.option("--tender-id", required=True, help="The tender ID to evaluate.")
def evaluate(tender_id: str) -> None:
    """Run the agentic evaluation workflow on a tender."""
    from .mcp_server import evaluate_bids

    result = asyncio.run(evaluate_bids(tender_id=tender_id))
    click.echo(result)


@cli.command()
@click.option("--tender-id", required=True, help="The tender ID.")
def report(tender_id: str) -> None:
    """Fetch the latest evaluation report for a tender."""
    from .mcp_server import get_report

    click.echo(get_report(tender_id=tender_id))


@cli.command()
@click.option("--tender-id", required=True, help="The tender ID.")
def audit(tender_id: str) -> None:
    """Fetch the full audit trail for a tender."""
    from .mcp_server import get_audit_trail

    click.echo(get_audit_trail(tender_id=tender_id))


@cli.command()
def tenders() -> None:
    """List all ingested tenders."""
    from .mcp_server import list_tenders

    click.echo(list_tenders())


@cli.command()
@click.option("--tender-id", required=True)
@click.option("--bid-id", required=True)
@click.option("--decision", type=click.Choice(["accept", "reject", "needs_review"]), required=True)
@click.option("--rationale", required=True, help=">=10 chars explaining the decision.")
@click.option(
    "--principal-id",
    default="officer-demo",
    help="The officer's principal ID (must NOT be 'agent').",
)
@click.option(
    "--principal-kind",
    type=click.Choice(["human", "agent"]),
    default="human",
)
def decide(
    tender_id: str,
    bid_id: str,
    decision: str,
    rationale: str,
    principal_id: str,
    principal_kind: str,
) -> None:
    """Record a procurement officer's decision on a bid. HUMAN-ONLY."""
    from .mcp_server import record_officer_decision

    click.echo(
        record_officer_decision(
            tender_id=tender_id,
            bid_id=bid_id,
            decision=decision,
            rationale=rationale,
            principal_id=principal_id,
            principal_kind=principal_kind,
        )
    )


@cli.command()
@click.option("--tender-id", required=True)
def demonstrate_human_in_the_loop(tender_id: str) -> None:
    """Demonstrate the human-in-the-loop boundary.

    Attempts to call `record_officer_decision` with `principal_kind='agent'`
    to show the refusal. This is for the live demo.
    """
    from .mcp_server import record_officer_decision

    click.echo("Attempting to record a decision with principal_kind='agent'...")
    result = record_officer_decision(
        tender_id=tender_id,
        bid_id="any-bid",
        decision="accept",
        rationale="agent attempt — should be refused",
        principal_id="bidbox-agent",
        principal_kind="agent",
    )
    click.echo(result)
    click.echo("\nThis is the human-in-the-loop rule, enforced at the tool layer.")
    click.echo("The SQL schema (CHECK + trigger) is the second line of defense.")


@cli.command()
def serve() -> None:
    """Start the FastAPI review UI."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "bidbox.api:app",
        host=settings.review_ui.host,
        port=settings.review_ui.port,
        reload=False,
    )


@cli.command()
def mcp() -> None:
    """Start the MCP server (stdio by default)."""
    from .mcp_server import main as mcp_main

    mcp_main()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
