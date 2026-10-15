"""Storage layer — SQLite (local dev) or Postgres (production / Vercel).

Two backends supported via the `DATABASE_URL` env var:

  * **SQLite** (default, when DATABASE_URL is unset): stdlib `sqlite3`,
    path = `UWAZI_DB_PATH` (default ./uwazi.db in cwd).
  * **Postgres** (when DATABASE_URL starts with `postgres://` or
    `postgresql://`): `psycopg2`. Backs Vercel Postgres / Neon /
    Supabase. Schema is portable — the BEFORE INSERT trigger on
    `decisions` is split into a function + trigger (Postgres form).

The query layer is written ONCE in SQLite dialect (`?` placeholders,
`INSERT OR REPLACE`). When running on Postgres, a thin connection
wrapper (`_PgConn`) intercepts every `execute()` call and:

  1. Converts `?` placeholders to `%s`.
  2. Rewrites `INSERT OR REPLACE INTO table (cols) VALUES (?)` to
     Postgres `INSERT INTO table (cols) VALUES (?) ON CONFLICT (id)
     DO UPDATE SET <cols = EXCLUDED.cols>`.

This means the rest of the code (Database class methods) is identical
between backends — no per-query branching needed.

The schema initialization is the only place that branches by backend
(see `_SCHEMA_SQLITE` vs `_SCHEMA_PG`).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .config import StorageConfig
from .models import (
    AuditEntry,
    Bid,
    BidResponse,
    Citation,
    Criterion,
    Decision,
    DecisionType,
    Document,
    Principal,
    PrincipalKind,
    Report,
    RiskFlag,
    Score,
    Tender,
)


# ===========================================================================
# SQLite schema (the canonical one)
# ===========================================================================

_SCHEMA_SQLITE = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenders (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    issuer        TEXT NOT NULL,
    country_code  TEXT NOT NULL,
    document_path TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bids (
    id            TEXT PRIMARY KEY,
    tender_id     TEXT NOT NULL REFERENCES tenders(id),
    bidder_name   TEXT NOT NULL,
    document_path TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('tender', 'bid')),
    parent_id     TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    paragraphs    TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS criteria (
    id            TEXT PRIMARY KEY,
    tender_id     TEXT NOT NULL REFERENCES tenders(id),
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    category      TEXT NOT NULL,
    weight        REAL NOT NULL,
    mandatory     INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
    citation      TEXT NOT NULL,
    ai_generated  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS responses (
    id            TEXT PRIMARY KEY,
    bid_id        TEXT NOT NULL REFERENCES bids(id),
    criterion_id  TEXT NOT NULL REFERENCES criteria(id),
    response_text TEXT NOT NULL,
    citation      TEXT NOT NULL,
    ai_generated  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scores (
    id              TEXT PRIMARY KEY,
    bid_id          TEXT NOT NULL REFERENCES bids(id),
    criterion_id    TEXT NOT NULL REFERENCES criteria(id),
    score           REAL NOT NULL CHECK (score BETWEEN 0 AND 10),
    rationale       TEXT NOT NULL,
    citation_tender TEXT NOT NULL,
    citation_bid    TEXT NOT NULL,
    ai_generated    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS risk_flags (
    id           TEXT PRIMARY KEY,
    bid_id       TEXT NOT NULL REFERENCES bids(id),
    risk_type    TEXT NOT NULL,
    severity     TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    description  TEXT NOT NULL,
    citation     TEXT NOT NULL,
    ai_generated INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reports (
    id                TEXT PRIMARY KEY,
    tender_id         TEXT NOT NULL REFERENCES tenders(id),
    generated_at      TEXT NOT NULL,
    bids              TEXT NOT NULL,
    ai_generated       INTEGER NOT NULL DEFAULT 1,
    correlation_id     TEXT NOT NULL,
    token_cost_cents  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    tender_id   TEXT NOT NULL REFERENCES tenders(id),
    bid_id      TEXT NOT NULL REFERENCES bids(id),
    decision    TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'needs_review')),
    rationale   TEXT NOT NULL,
    decided_by  TEXT NOT NULL,
    decided_at  TEXT NOT NULL,
    CHECK (decided_by <> 'agent')
);

CREATE TRIGGER IF NOT EXISTS decisions_no_agent_writer
BEFORE INSERT ON decisions
FOR EACH ROW
WHEN NEW.decided_by = 'agent'
BEGIN
    SELECT RAISE(ABORT, 'agent may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)');
END;

CREATE TABLE IF NOT EXISTS audit_trail (
    id          TEXT PRIMARY KEY,
    tender_id   TEXT NOT NULL REFERENCES tenders(id),
    bid_id      TEXT,
    entry_kind  TEXT NOT NULL CHECK (entry_kind IN ('ai_proposal', 'human_decision', 'tool_call')),
    actor       TEXT NOT NULL,
    actor_kind  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
"""


# ===========================================================================
# Postgres schema — same domain, dialect-appropriate syntax
# ===========================================================================

_SCHEMA_PG = """
-- Postgres version. Differences from SQLite:
--   * No PRAGMA (Postgres has no equivalent).
--   * The BEFORE INSERT trigger on `decisions` is split into a
--     FUNCTION (RETURNS TRIGGER) + CREATE TRIGGER. Postgres requires
--     the function form for triggers that conditionally RAISE.

CREATE TABLE IF NOT EXISTS tenders (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    issuer        TEXT NOT NULL,
    country_code  TEXT NOT NULL,
    document_path TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bids (
    id            TEXT PRIMARY KEY,
    tender_id     TEXT NOT NULL REFERENCES tenders(id),
    bidder_name   TEXT NOT NULL,
    document_path TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('tender', 'bid')),
    parent_id     TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    paragraphs    TEXT NOT NULL,
    ingested_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS criteria (
    id            TEXT PRIMARY KEY,
    tender_id     TEXT NOT NULL REFERENCES tenders(id),
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    category      TEXT NOT NULL,
    weight        DOUBLE PRECISION NOT NULL,
    mandatory     INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
    citation      TEXT NOT NULL,
    ai_generated  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS responses (
    id            TEXT PRIMARY KEY,
    bid_id        TEXT NOT NULL REFERENCES bids(id),
    criterion_id  TEXT NOT NULL REFERENCES criteria(id),
    response_text TEXT NOT NULL,
    citation      TEXT NOT NULL,
    ai_generated  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scores (
    id              TEXT PRIMARY KEY,
    bid_id          TEXT NOT NULL REFERENCES bids(id),
    criterion_id    TEXT NOT NULL REFERENCES criteria(id),
    score           DOUBLE PRECISION NOT NULL CHECK (score BETWEEN 0 AND 10),
    rationale       TEXT NOT NULL,
    citation_tender TEXT NOT NULL,
    citation_bid    TEXT NOT NULL,
    ai_generated    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS risk_flags (
    id           TEXT PRIMARY KEY,
    bid_id       TEXT NOT NULL REFERENCES bids(id),
    risk_type    TEXT NOT NULL,
    severity     TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    description  TEXT NOT NULL,
    citation     TEXT NOT NULL,
    ai_generated INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS reports (
    id                TEXT PRIMARY KEY,
    tender_id         TEXT NOT NULL REFERENCES tenders(id),
    generated_at      TEXT NOT NULL,
    bids              TEXT NOT NULL,
    ai_generated       INTEGER NOT NULL DEFAULT 1,
    correlation_id     TEXT NOT NULL,
    token_cost_cents  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    tender_id   TEXT NOT NULL REFERENCES tenders(id),
    bid_id      TEXT NOT NULL REFERENCES bids(id),
    decision    TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'needs_review')),
    rationale   TEXT NOT NULL,
    decided_by  TEXT NOT NULL,
    decided_at  TEXT NOT NULL,
    CHECK (decided_by <> 'agent')
);

-- The human-in-the-loop rule, enforced at the SQL layer (Postgres form).
-- See ARCHITECTURE.md §5. Splits the SQLite trigger into a function +
-- trigger, as required by Postgres.
CREATE OR REPLACE FUNCTION refuse_agent_decision_writer()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.decided_by = 'agent' THEN
        RAISE EXCEPTION 'agent may not record decisions — human-in-the-loop rule (ARCHITECTURE.md §5)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS decisions_no_agent_writer ON decisions;
CREATE TRIGGER decisions_no_agent_writer
BEFORE INSERT ON decisions
FOR EACH ROW
EXECUTE FUNCTION refuse_agent_decision_writer();

CREATE TABLE IF NOT EXISTS audit_trail (
    id          TEXT PRIMARY KEY,
    tender_id   TEXT NOT NULL REFERENCES tenders(id),
    bid_id      TEXT,
    entry_kind  TEXT NOT NULL CHECK (entry_kind IN ('ai_proposal', 'human_decision', 'tool_call')),
    actor       TEXT NOT NULL,
    actor_kind  TEXT NOT NULL,
    payload     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
"""


# ===========================================================================
# Postgres query rewriter — converts SQLite dialect on the fly
# ===========================================================================

# Regex: match `INSERT OR REPLACE INTO table (cols) VALUES (placeholders)`
# and capture the table name, column list, and placeholders.
_INSERT_OR_REPLACE_RE = re.compile(
    r'INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)',
    re.IGNORECASE | re.DOTALL,
)


def _convert_query_to_postgres(query: str) -> str:
    """Convert a SQLite-dialect SQL string to Postgres-compatible SQL.

    Two transformations:
      1. `?` placeholders → `%s` (Postgres style).
      2. `INSERT OR REPLACE INTO table (cols) VALUES (...)` →
         `INSERT INTO table (cols) VALUES (...) ON CONFLICT (id)
         DO UPDATE SET <non-id cols = EXCLUDED.cols>`.
    """
    # 1. Placeholders.
    query = re.sub(r"\?", "%s", query)
    # 2. INSERT OR REPLACE → ON CONFLICT DO UPDATE (UPSERT).
    def _upsert(match: "re.Match[str]") -> str:
        table = match.group(1)
        cols_str = match.group(2).strip()
        placeholders_str = match.group(3).strip()
        cols = [c.strip() for c in cols_str.split(",")]
        # The PK column is always 'id' for our schema.
        non_pk_cols = [c for c in cols if c != "id"]
        if not non_pk_cols:
            # Only the id column — use ON CONFLICT DO NOTHING.
            return (
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders_str}) "
                f"ON CONFLICT (id) DO NOTHING"
            )
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk_cols)
        return (
            f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders_str}) "
            f"ON CONFLICT (id) DO UPDATE SET {set_clause}"
        )
    query = _INSERT_OR_REPLACE_RE.sub(_upsert, query)
    return query


class _PgConn:
    """Thin wrapper around a psycopg2 connection that auto-converts
    SQLite-dialect SQL to Postgres on every `execute()` / `executescript()`.

    The rest of the Database class methods can call `self._conn.execute(...)`
    exactly as they did for SQLite — the wrapper handles conversion.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, query: str, params: tuple | None = None):
        q = _convert_query_to_postgres(query)
        cur = self._conn.cursor()
        if params is None:
            cur.execute(q)
        else:
            cur.execute(q, params)
        return cur

    def executescript(self, script: str) -> None:
        # psycopg2 doesn't have executescript; run as one big execute.
        # The script may contain multiple statements separated by ; —
        # psycopg2 handles that natively in a single execute call.
        cur = self._conn.cursor()
        cur.execute(script)
        cur.close()

    def close(self) -> None:
        self._conn.close()

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        # psycopg2 with RealDictCursor uses cursor_factory on the conn,
        # not row_factory. Setting this is a no-op — we set the cursor
        # factory at construction time. So accept and ignore.
        pass

    def __getattr__(self, name: str):
        """Pass-through for any other methods (commit, rollback, cursor)."""
        return getattr(self._conn, name)


# ===========================================================================
# The Database class — one query layer, two backends
# ===========================================================================


class Database:
    """Dual-backend storage. SQLite for local dev; Postgres for production.

    Backend is selected at construction time from `StorageConfig.backend`:

      * `sqlite` (default, when DATABASE_URL is unset)
      * `postgres` (when DATABASE_URL starts with postgres:// or postgresql://)
    """

    def __init__(self, config: StorageConfig | None = None) -> None:
        self._config = config or StorageConfig()
        self._lock = threading.RLock()
        self._backend = self._config.backend

        if self._backend == "postgres":
            self._init_postgres()
        else:
            self._init_sqlite()

    # ------------------------------------------------------------------
    # Backend init
    # ------------------------------------------------------------------

    def _init_sqlite(self) -> None:
        self._conn = sqlite3.connect(
            str(self._config.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage txns manually
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA_SQLITE)

    def _init_postgres(self) -> None:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 not installed — run `pip install psycopg2-binary` "
                "or unset DATABASE_URL to fall back to SQLite"
            ) from exc

        conn = psycopg2.connect(self._config.database_url)
        conn.autocommit = True  # we manage txns manually via BEGIN/COMMIT
        # Wrap so every execute() is SQLite→Postgres converted on the fly.
        self._conn = _PgConn(conn)
        # RealDictCursor makes rows behave like dicts (sqlite3.Row compatible).
        conn.cursor_factory = RealDictCursor
        # Run the schema. Postgres allows multi-statement execute in one call.
        with self._lock:
            self._conn.executescript(_SCHEMA_PG)

    @property
    def backend(self) -> str:
        return self._backend

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Wrap a write transaction. Commits on success, rolls back on error."""
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Tenders
    # ------------------------------------------------------------------

    def save_tender(self, t: Tender) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tenders
                   (id, title, issuer, country_code, document_path, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (t.id, t.title, t.issuer, t.country_code, t.document_path, _iso(t.ingested_at)),
            )

    def get_tender(self, tender_id: str) -> Tender | None:
        row = self._conn.execute(
            "SELECT * FROM tenders WHERE id = ?", (tender_id,)
        ).fetchone()
        return _tender_from_row(row) if row else None

    def list_tenders(self) -> list[Tender]:
        rows = self._conn.execute(
            "SELECT * FROM tenders ORDER BY ingested_at DESC"
        ).fetchall()
        return [_tender_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Bids
    # ------------------------------------------------------------------

    def save_bid(self, b: Bid) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO bids
                   (id, tender_id, bidder_name, document_path, ingested_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (b.id, b.tender_id, b.bidder_name, b.document_path, _iso(b.ingested_at)),
            )

    def list_bids(self, tender_id: str) -> list[Bid]:
        rows = self._conn.execute(
            "SELECT * FROM bids WHERE tender_id = ? ORDER BY ingested_at", (tender_id,)
        ).fetchall()
        return [_bid_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def save_document(self, doc: Document) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, kind, parent_id, source_path, paragraphs, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    doc.id,
                    doc.kind,
                    doc.parent_id,
                    doc.source_path,
                    json.dumps(doc.paragraphs),
                    _iso(doc.ingested_at),
                ),
            )

    def get_document(self, doc_id: str) -> Document | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return _document_from_row(row) if row else None

    # ------------------------------------------------------------------
    # Criteria
    # ------------------------------------------------------------------

    def save_criterion(self, c: Criterion) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO criteria
                   (id, tender_id, name, description, category, weight, mandatory,
                    citation, ai_generated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    c.id,
                    c.tender_id,
                    c.name,
                    c.description,
                    c.category.value,
                    c.weight,
                    int(c.mandatory),
                    c.citation.model_dump_json(),
                ),
            )

    def list_criteria(self, tender_id: str) -> list[Criterion]:
        rows = self._conn.execute(
            "SELECT * FROM criteria WHERE tender_id = ? ORDER BY id", (tender_id,)
        ).fetchall()
        return [_criterion_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Responses, scores, risk flags
    # ------------------------------------------------------------------

    def save_response(self, r: BidResponse) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO responses
                   (id, bid_id, criterion_id, response_text, citation, ai_generated)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (r.id, r.bid_id, r.criterion_id, r.response_text, r.citation.model_dump_json()),
            )

    def save_score(self, s: Score) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scores
                   (id, bid_id, criterion_id, score, rationale,
                    citation_tender, citation_bid, ai_generated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    s.id,
                    s.bid_id,
                    s.criterion_id,
                    s.score,
                    s.rationale,
                    s.citation_tender.model_dump_json(),
                    s.citation_bid.model_dump_json(),
                ),
            )

    def save_risk_flag(self, r: RiskFlag) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO risk_flags
                   (id, bid_id, risk_type, severity, description, citation, ai_generated)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (
                    r.id,
                    r.bid_id,
                    r.risk_type,
                    r.severity,
                    r.description,
                    r.citation.model_dump_json(),
                ),
            )

    def list_scores(self, tender_id: str, bid_id: str) -> list[Score]:
        rows = self._conn.execute(
            """SELECT s.* FROM scores s
               JOIN criteria c ON s.criterion_id = c.id
               WHERE c.tender_id = ? AND s.bid_id = ?
               ORDER BY c.id""",
            (tender_id, bid_id),
        ).fetchall()
        return [_score_from_row(r) for r in rows]

    def list_risk_flags(self, bid_id: str) -> list[RiskFlag]:
        rows = self._conn.execute(
            "SELECT * FROM risk_flags WHERE bid_id = ? ORDER BY severity DESC, id",
            (bid_id,),
        ).fetchall()
        return [_risk_flag_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def save_report(self, r: Report) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO reports
                   (id, tender_id, generated_at, bids, ai_generated,
                    correlation_id, token_cost_cents)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (
                    str(r.id),
                    r.tender_id,
                    _iso(r.generated_at),
                    json.dumps([b.model_dump(mode="json") for b in r.bids]),
                    r.correlation_id,
                    str(r.token_cost_cents),
                ),
            )

    def get_latest_report(self, tender_id: str) -> Report | None:
        row = self._conn.execute(
            "SELECT * FROM reports WHERE tender_id = ? ORDER BY generated_at DESC LIMIT 1",
            (tender_id,),
        ).fetchone()
        return _report_from_row(row) if row else None

    # ------------------------------------------------------------------
    # Decisions — HUMAN-ONLY
    # ------------------------------------------------------------------

    def save_decision(self, d: Decision) -> None:
        """Save a procurement officer decision.

        Raises IntegrityError if `decided_by='agent'` — see the trigger
        in _SCHEMA_SQLITE / _SCHEMA_PG. This is the human-in-the-loop
        rule, enforced at the SQL layer.
        """
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO decisions
                   (id, tender_id, bid_id, decision, rationale,
                    decided_by, decided_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    d.id,
                    d.tender_id,
                    d.bid_id,
                    d.decision.value,
                    d.rationale,
                    d.decided_by,
                    _iso(d.decided_at),
                ),
            )

    def list_decisions(self, tender_id: str) -> list[Decision]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE tender_id = ? ORDER BY decided_at",
            (tender_id,),
        ).fetchall()
        return [_decision_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def append_audit(self, entry: AuditEntry) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO audit_trail
                   (id, tender_id, bid_id, entry_kind, actor, actor_kind,
                    payload, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.tender_id,
                    entry.bid_id,
                    entry.entry_kind,
                    entry.actor,
                    entry.actor_kind.value,
                    json.dumps(entry.payload),
                    _iso(entry.timestamp),
                ),
            )

    def list_audit(self, tender_id: str) -> list[AuditEntry]:
        rows = self._conn.execute(
            "SELECT * FROM audit_trail WHERE tender_id = ? ORDER BY timestamp",
            (tender_id,),
        ).fetchall()
        return [_audit_from_row(r) for r in rows]


# ===========================================================================
# Row → model deserialisers (work identically for both backends because
# both sqlite3.Row and psycopg2 RealDictRow support dict-style access)
# ===========================================================================


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _tender_from_row(row: Any) -> Tender:
    return Tender(
        id=row["id"],
        title=row["title"],
        issuer=row["issuer"],
        country_code=row["country_code"],
        document_path=row["document_path"],
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def _bid_from_row(row: Any) -> Bid:
    return Bid(
        id=row["id"],
        tender_id=row["tender_id"],
        bidder_name=row["bidder_name"],
        document_path=row["document_path"],
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def _document_from_row(row: Any) -> Document:
    return Document(
        id=row["id"],
        kind=row["kind"],  # type: ignore[arg-type]
        parent_id=row["parent_id"],
        source_path=row["source_path"],
        paragraphs=json.loads(row["paragraphs"]),
        ingested_at=datetime.fromisoformat(row["ingested_at"]),
    )


def _criterion_from_row(row: Any) -> Criterion:
    return Criterion(
        id=row["id"],
        tender_id=row["tender_id"],
        name=row["name"],
        description=row["description"],
        category=row["category"],  # type: ignore[arg-type]
        weight=row["weight"],
        mandatory=bool(row["mandatory"]),
        citation=Citation.model_validate_json(row["citation"]),
        ai_generated=bool(row["ai_generated"]),
    )


def _score_from_row(row: Any) -> Score:
    return Score(
        id=row["id"],
        bid_id=row["bid_id"],
        criterion_id=row["criterion_id"],
        score=row["score"],
        rationale=row["rationale"],
        citation_tender=Citation.model_validate_json(row["citation_tender"]),
        citation_bid=Citation.model_validate_json(row["citation_bid"]),
        ai_generated=bool(row["ai_generated"]),
    )


def _risk_flag_from_row(row: Any) -> RiskFlag:
    return RiskFlag(
        id=row["id"],
        bid_id=row["bid_id"],
        risk_type=row["risk_type"],
        severity=row["severity"],  # type: ignore[arg-type]
        description=row["description"],
        citation=Citation.model_validate_json(row["citation"]),
        ai_generated=bool(row["ai_generated"]),
    )


def _decision_from_row(row: Any) -> Decision:
    return Decision(
        id=row["id"],
        tender_id=row["tender_id"],
        bid_id=row["bid_id"],
        decision=DecisionType(row["decision"]),
        rationale=row["rationale"],
        decided_by=row["decided_by"],
        decided_at=datetime.fromisoformat(row["decided_at"]),
    )


def _report_from_row(row: Any) -> Report:
    from .models import BidEvaluation

    bids_data = json.loads(row["bids"])
    return Report(
        id=row["id"],  # type: ignore[arg-type]
        tender_id=row["tender_id"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        bids=[BidEvaluation.model_validate(b) for b in bids_data],
        ai_generated=bool(row["ai_generated"]),
        correlation_id=row["correlation_id"],
        token_cost_cents=Decimal(row["token_cost_cents"]),
    )


def _audit_from_row(row: Any) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        tender_id=row["tender_id"],
        bid_id=row["bid_id"],
        entry_kind=row["entry_kind"],  # type: ignore[arg-type]
        actor=row["actor"],
        actor_kind=PrincipalKind(row["actor_kind"]),
        payload=json.loads(row["payload"]),
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )


# ===========================================================================
# Helpers
# ===========================================================================


def new_id(prefix: str) -> str:
    """Generate a stable ID with a prefix and a short uuid suffix."""
    return f"{prefix}-{uuid4().hex[:12]}"


def in_memory_db() -> Database:
    """Return a Database backed by an in-memory SQLite (for tests)."""
    cfg = StorageConfig(db_path=Path(":memory:"))  # type: ignore[arg-type]
    return Database(cfg)


# Module-level singleton for the running app
_DB: Database | None = None


def get_db() -> Database:
    """Return the process-wide Database singleton."""
    global _DB
    if _DB is None:
        _DB = Database()
    return _DB


def reset_db_for_tests() -> Database:
    """Replace the singleton with an in-memory DB; return it."""
    global _DB
    _DB = in_memory_db()
    return _DB
