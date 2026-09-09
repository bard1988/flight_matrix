"""SQLite cache so reopening a board, or nudging the anchor date by a day, is cheap."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, timedelta
from typing import Any, Iterable

import config
from config import CACHE_DB, DATA_DIR
from models import Cell, DestinationMatrix, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cells (
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    price REAL NOT NULL,
    airline TEXT,
    transfers INTEGER,
    return_transfers INTEGER,
    found_at TEXT,
    expires_at TEXT,
    link TEXT,
    fetched_at TEXT NOT NULL,
    source TEXT,
    is_total INTEGER DEFAULT 0,
    checked INTEGER DEFAULT 0,
    fill_version INTEGER NOT NULL DEFAULT 0,
    party TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (origin, destination, depart_date, return_date, currency, party)
);

CREATE TABLE IF NOT EXISTS verified (
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT NOT NULL,
    adults INTEGER NOT NULL,
    children INTEGER NOT NULL,
    currency TEXT NOT NULL,
    total REAL,
    airline TEXT,
    stops_out INTEGER,
    stops_back INTEGER,
    duration TEXT,
    link TEXT,
    error TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (origin, destination, depart_date, return_date, adults, children, currency)
);

CREATE TABLE IF NOT EXISTS searches (
    id TEXT PRIMARY KEY,
    params TEXT NOT NULL,
    board TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS cells_route ON cells (origin, destination, currency);
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # Serving several people at once means a board fill is writing while other boards
        # are reading. In the default rollback journal those block each other; WAL lets
        # readers through, and the busy timeout absorbs the remaining write contention
        # instead of surfacing "database is locked" to a user mid-search.
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(_SCHEMA)
        _migrate(_conn)
        _conn.commit()
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add parser_version to `verified` for databases created before it existed.

    Rows without it were produced by the old parser that read only one of Google's
    itinerary blocks and so understated many cells; they default to version 0 and are
    filtered out by the readers, which makes them re-fetch.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(verified)")}
    if "parser_version" not in columns:
        conn.execute("ALTER TABLE verified ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 0")

    # `source` / `is_total` record which provider a cell came from and whether its price
    # already covers the whole party. Older rows predate multi-provider support.
    # Flight times for a verified cell, so the panel can show when you actually fly.
    for column in ("departs", "arrives", "segments"):
        if column not in columns:
            conn.execute(f"ALTER TABLE verified ADD COLUMN {column} TEXT")

    cell_columns = {row["name"] for row in conn.execute("PRAGMA table_info(cells)")}
    if "source" not in cell_columns:
        conn.execute("ALTER TABLE cells ADD COLUMN source TEXT")
    if "is_total" not in cell_columns:
        conn.execute("ALTER TABLE cells ADD COLUMN is_total INTEGER DEFAULT 0")
    if "checked" not in cell_columns:
        conn.execute("ALTER TABLE cells ADD COLUMN checked INTEGER DEFAULT 0")
    if "fill_version" not in cell_columns:
        conn.execute(
            "ALTER TABLE cells ADD COLUMN fill_version INTEGER NOT NULL DEFAULT 0")

    if "party" not in cell_columns:
        # The passenger mix belongs in the KEY, not just the row: a party total is only
        # valid for the mix it was priced for, and the old key let a 2-adult grid be
        # served whole to a 2-adult-3-children search at two fifths of the real price.
        # SQLite cannot extend a primary key in place, so rebuild the table. Per-ticket
        # rows (is_total=0) are mix-independent and carry party=''; the existing totals
        # cannot be attributed to a mix after the fact, so they are dropped rather than
        # kept under a guess.
        conn.executescript(_CELLS_REBUILD)



_CELLS_REBUILD = """
ALTER TABLE cells RENAME TO cells_old;
CREATE TABLE cells (
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    price REAL NOT NULL,
    airline TEXT,
    transfers INTEGER,
    return_transfers INTEGER,
    found_at TEXT,
    expires_at TEXT,
    link TEXT,
    fetched_at TEXT NOT NULL,
    source TEXT,
    is_total INTEGER DEFAULT 0,
    checked INTEGER DEFAULT 0,
    party TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (origin, destination, depart_date, return_date, currency, party)
);
INSERT OR REPLACE INTO cells
    (origin, destination, depart_date, return_date, currency, price, airline, transfers,
     return_transfers, found_at, expires_at, link, fetched_at, source, is_total, checked, party)
SELECT origin, destination, depart_date, return_date, currency, price, airline, transfers,
       return_transfers, found_at, expires_at, link, fetched_at, source, 0, 0, ''
FROM cells_old WHERE COALESCE(is_total, 0) = 0;
DROP TABLE cells_old;
"""

def put_cells(
    origin: str,
    destination: str,
    currency: str,
    cells: Iterable[Cell],
    party: str = "",
) -> int:
    """Store cells. `party` is the passenger mix a TOTAL was priced for (see get_matrix)."""
    conn = connect()
    now = utcnow().isoformat()
    rows = [
        (
            origin.upper(), destination.upper(), c.depart_date, c.return_date, currency,
            c.price, c.airline, c.transfers, c.return_transfers,
            c.found_at, c.expires_at, c.link, now, c.source, 1 if c.is_total else 0,
            1 if c.checked else 0, config.FILL_VERSION, party if c.is_total else "",
        )
        for c in cells
    ]
    if not rows:
        return 0
    with _lock:
        conn.executemany(
            "INSERT OR REPLACE INTO cells (origin, destination, depart_date, return_date,"
            " currency, price, airline, transfers, return_transfers, found_at, expires_at,"
            " link, fetched_at, source, is_total, checked, fill_version, party)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    return len(rows)


def get_matrix(
    origin: str,
    destination: str,
    currency: str,
    depart_dates: list[date],
    return_dates: list[date],
    max_age_hours: float | None = None,
    source: str | None = None,
    party: str = "",
) -> DestinationMatrix:
    """Cells previously fetched for this route and window.

    `max_age_hours` limits results to recently fetched rows, which is how the board avoids
    re-querying a provider that rate-limits.

    `party` is the passenger mix being searched for. Rows holding a party TOTAL come back
    only when they were priced for that same mix; per-ticket rows are mix-independent and
    always match, since the caller scales them itself.
    """
    conn = connect()
    sql = ("SELECT * FROM cells WHERE origin=? AND destination=? AND currency=?"
           " AND depart_date BETWEEN ? AND ? AND return_date BETWEEN ? AND ?")
    params: list[Any] = [
        origin.upper(), destination.upper(), currency,
        depart_dates[0].isoformat(), depart_dates[-1].isoformat(),
        return_dates[0].isoformat(), return_dates[-1].isoformat(),
    ]
    if max_age_hours is not None:
        cutoff = (utcnow() - timedelta(hours=max_age_hours)).isoformat()
        sql += " AND fetched_at >= ?"
        params.append(cutoff)
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    sql += " AND (is_total = 0 OR party = ?)"
    params.append(party)
    # Cells written by an older fill strategy are wrong, not stale: serve none of them.
    sql += " AND fill_version >= ?"
    params.append(config.FILL_VERSION)
    with _lock:
        rows = conn.execute(sql, params).fetchall()
    matrix = DestinationMatrix(origin=origin.upper(), destination=destination.upper())
    for row in rows:
        matrix.add(
            Cell(
                depart_date=row["depart_date"],
                return_date=row["return_date"],
                price=row["price"],
                currency=row["currency"],
                airline=row["airline"],
                transfers=row["transfers"],
                return_transfers=row["return_transfers"],
                found_at=row["found_at"],
                expires_at=row["expires_at"],
                link=row["link"],
                source=row["source"] or "travelpayouts",
                is_total=bool(row["is_total"]),
                checked=bool(row["checked"]),
            )
        )
    return matrix


def put_verified(record: dict[str, Any]) -> None:
    conn = connect()
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO verified (origin, destination, depart_date, return_date,"
            " adults, children, currency, total, airline, stops_out, stops_back, duration,"
            " link, error, fetched_at, parser_version, departs, arrives, segments)"
            " VALUES (:origin,:destination,"
            ":depart_date,:return_date,:adults,:children,:currency,:total,:airline,"
            ":stops_out,:stops_back,:duration,:link,:error,:fetched_at,:parser_version,"
            ":departs,:arrives,:segments)",
            {
                "departs": None, "arrives": None, "segments": None,
                **record,
                "fetched_at": utcnow().isoformat(),
                "parser_version": record.get("parser_version", config.PARSER_VERSION),
                "segments": json.dumps(record["segments"]) if record.get("segments") else None,
            },
        )
        conn.commit()


def get_verified(
    origin: str, destination: str, depart_date: str, return_date: str,
    adults: int, children: int, currency: str,
) -> dict[str, Any] | None:
    conn = connect()
    with _lock:
        row = conn.execute(
            "SELECT * FROM verified WHERE origin=? AND destination=? AND depart_date=?"
            " AND return_date=? AND adults=? AND children=? AND currency=?"
            " AND parser_version >= ?",
            (origin.upper(), destination.upper(), depart_date, return_date, adults, children,
             currency, config.PARSER_VERSION),
        ).fetchone()
    return dict(row) if row else None


def get_all_verified(
    origin: str, adults: int, children: int, currency: str
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Every verified cell for this origin and passenger mix, keyed by (dest, depart, return)."""
    conn = connect()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM verified WHERE origin=? AND adults=? AND children=? AND currency=?"
            " AND total IS NOT NULL AND parser_version >= ?",
            (origin.upper(), adults, children, currency, config.PARSER_VERSION),
        ).fetchall()
    return {(r["destination"], r["depart_date"], r["return_date"]): dict(r) for r in rows}


def unpriceable_destinations(
    origin: str, adults: int, children: int, currency: str, min_failures: int = 3
) -> set[str]:
    """Destinations Google Flights has repeatedly failed to price, with no success ever.

    Some routes simply are not in Google's data (measured: TLV to Ramon/ETM failed on all
    40 attempts). Without this, every cross-check would burn its whole budget re-failing
    the same route.
    """
    conn = connect()
    with _lock:
        rows = conn.execute(
            "SELECT destination, SUM(total IS NULL) failures, SUM(total IS NOT NULL) hits"
            " FROM verified WHERE origin=? AND adults=? AND children=? AND currency=?"
            " GROUP BY destination",
            (origin.upper(), adults, children, currency),
        ).fetchall()
    return {
        r["destination"] for r in rows
        if (r["failures"] or 0) >= min_failures and not (r["hits"] or 0)
    }


def create_search(search_id: str, params: dict[str, Any]) -> None:
    conn = connect()
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO searches (id, params, board, status, created_at) VALUES (?,?,?,?,?)",
            (search_id, json.dumps(params), None, "running", utcnow().isoformat()),
        )
        conn.commit()


def finish_search(search_id: str, board: dict[str, Any], status: str = "done") -> None:
    conn = connect()
    with _lock:
        conn.execute(
            "UPDATE searches SET board=?, status=? WHERE id=?",
            (json.dumps(board), status, search_id),
        )
        # A saved board runs to ~1.8 MB of JSON and nothing ever deleted one: 324 rows had
        # grown to 69 MB of a 77 MB database. Keep the most recent ones so an old link
        # still resolves, and drop the tail.
        if config.SEARCH_HISTORY_KEEP > 0:
            conn.execute(
                "DELETE FROM searches WHERE id NOT IN ("
                " SELECT id FROM searches ORDER BY created_at DESC LIMIT ?)",
                (config.SEARCH_HISTORY_KEEP,),
            )
        conn.commit()


def get_search(search_id: str) -> dict[str, Any] | None:
    conn = connect()
    with _lock:
        row = conn.execute("SELECT * FROM searches WHERE id=?", (search_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "params": json.loads(row["params"]),
        "board": json.loads(row["board"]) if row["board"] else None,
        "status": row["status"],
        "created_at": row["created_at"],
    }
